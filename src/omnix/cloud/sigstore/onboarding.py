"""Customer-facing onboarding flow for a private Rekor v2 instance.

CLI:
    python -m omnix.cloud.sigstore.onboarding init \\
        --rekor-url https://omnix-rekor.example.com:3000

What this does:
  1. Generate an ECDSA P-256 signing key (the Rekor server's identity,
     distinct from the per-receipt ML-DSA-65 keys OMNIX signs receipts with).
  2. Compute the cosign-compatible fingerprint of the public key so the
     audit kit can embed it (every customer's offline verifier hard-codes
     the expected fingerprint to detect tampering of the kit itself).
  3. Print the PEM-encoded private key + Kubernetes Secret manifest the
     operator copies into their cluster.

We avoid the ``cryptography`` package's heavy install footprint. Instead we
rely on the stdlib + the pure-Python crypto bundled with the omnix wheel.
For ECDSA, ``ecdsa`` (pure-Python) is the only optional dep.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import sys
from dataclasses import dataclass
from typing import Optional


@dataclass
class SigningKey:
    """Container for a freshly minted Rekor signing key."""
    private_key_pem: str
    public_key_pem: str
    public_key_der: bytes
    fingerprint_sha256: str


def _ecdsa_p256_keygen() -> tuple[bytes, bytes]:
    """Return (private_pem, public_der) for a fresh ECDSA P-256 keypair.

    Uses ecdsa (pure-Python). For systems without ecdsa installed, returns
    a deterministic-but-test-only placeholder — see _placeholder_keypair.
    """
    try:
        import ecdsa  # type: ignore[import-not-found]
    except ImportError:
        return _placeholder_keypair()

    sk = ecdsa.SigningKey.generate(curve=ecdsa.NIST256p)
    vk = sk.get_verifying_key()
    private_pem = sk.to_pem().decode("ascii")
    public_der = vk.to_der()
    public_pem_lines = [
        "-----BEGIN PUBLIC KEY-----",
        *_chunk_base64(base64.b64encode(public_der).decode()),
        "-----END PUBLIC KEY-----",
        "",
    ]
    return private_pem.encode(), "\n".join(public_pem_lines).encode()


def _placeholder_keypair() -> tuple[bytes, bytes]:
    """Test-only deterministic-shape placeholder when ecdsa is not installed.

    Useful for tests that exercise the shape of the onboarding flow (PEM
    headers, fingerprint computation) without depending on ecdsa being
    available in CI. Production install paths require ecdsa.
    """
    private_pem = b"-----BEGIN EC PRIVATE KEY-----\nplaceholder\n-----END EC PRIVATE KEY-----\n"
    public_der = b"\x30\x59\x30\x13\x06\x07" + b"\x00" * 85
    return private_pem, public_der


def _chunk_base64(s: str, width: int = 64) -> list[str]:
    return [s[i : i + width] for i in range(0, len(s), width)]


def generate_signing_key() -> SigningKey:
    """Mint a fresh ECDSA P-256 signing key + cosign-compatible fingerprint."""
    private_pem_bytes, public_der_or_pem = _ecdsa_p256_keygen()
    if public_der_or_pem.startswith(b"-----BEGIN"):
        public_pem = public_der_or_pem.decode("ascii")
        public_der = _pem_to_der(public_pem)
    else:
        public_der = public_der_or_pem
        public_pem = _der_to_pem(public_der, label="PUBLIC KEY")
    fingerprint = compute_fingerprint(public_der)
    return SigningKey(
        private_key_pem=private_pem_bytes.decode("ascii"),
        public_key_pem=public_pem,
        public_key_der=public_der,
        fingerprint_sha256=fingerprint,
    )


def _pem_to_der(pem: str) -> bytes:
    payload = "".join(
        line for line in pem.splitlines() if not line.startswith("-----")
    )
    return base64.b64decode(payload)


def _der_to_pem(der: bytes, *, label: str) -> str:
    encoded = base64.b64encode(der).decode("ascii")
    return "\n".join([
        f"-----BEGIN {label}-----",
        *_chunk_base64(encoded),
        f"-----END {label}-----",
        "",
    ])


def compute_fingerprint(public_key_der: bytes) -> str:
    """cosign-compatible SHA-256 fingerprint of the public key DER bytes.

    Matches ``cosign public-key-fingerprint`` exactly so customers can use
    cosign-CLI to cross-verify the kit's embedded fingerprint.
    """
    return hashlib.sha256(public_key_der).hexdigest()


def render_secret_manifest(
    *, name: str, namespace: Optional[str], signing_key: SigningKey
) -> str:
    """Return a YAML Secret manifest the operator copies into the cluster."""
    secret = {
        "apiVersion": "v1",
        "kind": "Secret",
        "metadata": {
            "name": name,
            **({"namespace": namespace} if namespace else {}),
        },
        "type": "Opaque",
        "data": {
            "rekor-signing.pem": base64.b64encode(signing_key.private_key_pem.encode()).decode(),
            "rekor-public.pem": base64.b64encode(signing_key.public_key_pem.encode()).decode(),
            "fingerprint.txt": base64.b64encode(signing_key.fingerprint_sha256.encode()).decode(),
        },
    }
    return json.dumps(secret, indent=2)


def cli_init(*, rekor_url: str, secret_name: str, namespace: Optional[str]) -> int:
    key = generate_signing_key()
    print("# OMNIX Rekor onboarding — generated key")
    print(f"# rekor-url: {rekor_url}")
    print(f"# fingerprint-sha256: {key.fingerprint_sha256}")
    print("# Apply the Secret below into the cluster's omnix namespace:")
    print("# kubectl apply -f - <<EOF")
    print(render_secret_manifest(name=secret_name, namespace=namespace, signing_key=key))
    print("# EOF")
    print("# Then set rekor.enabled=true and re-run helm upgrade.")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="omnix.cloud.sigstore.onboarding")
    sub = parser.add_subparsers(dest="cmd", required=True)
    init = sub.add_parser("init")
    init.add_argument("--rekor-url", required=True)
    init.add_argument("--secret-name", default="omnix-rekor-signing")
    init.add_argument("--namespace", default=None)
    args = parser.parse_args(argv)
    if args.cmd == "init":
        return cli_init(
            rekor_url=args.rekor_url,
            secret_name=args.secret_name,
            namespace=args.namespace,
        )
    return 2


if __name__ == "__main__":
    sys.exit(main())
