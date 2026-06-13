# Compliance: P11, P15, P19, P20, P22

"""
PEM wrapping for OMNIX AXIOM ML-DSA-65 (raw FIPS-204 key/signature bytes).
"""

from __future__ import annotations

import base64
import getpass
import os
import subprocess
from pathlib import Path

from . import params as P


def harden_permissions(path: Path | str) -> None:
    """Restrict a secret file to its owner, cross-platform.

    POSIX: ``chmod 0600``. On Windows ``os.chmod(.., 0o600)`` is effectively a
    no-op (it only toggles the read-only bit), leaving private keys readable
    by every account on the box. There we reset the ACL via ``icacls``.

    The Windows sequence is lock-out-safe: we ADD an explicit full-control ACE
    for the current user FIRST, and only break inheritance if that grant
    succeeded — so a failed/garbled principal can never strip the owner's own
    access. Any icacls failure leaves the (inherited) ACL untouched.
    """
    p = Path(path)
    if os.name != "nt":
        try:
            os.chmod(p, 0o600)
        except OSError:
            pass
        return
    # Windows
    try:
        user = getpass.getuser()
    except Exception:  # noqa: BLE001
        user = os.environ.get("USERNAME", "")
    if not user:
        return
    try:
        granted = subprocess.run(
            ["icacls", str(p), "/grant", f"{user}:(F)"],
            capture_output=True, text=True, check=False,
        )
        if granted.returncode == 0:
            # User now has an explicit ACE; safe to drop inherited ACEs.
            subprocess.run(
                ["icacls", str(p), "/inheritance:r"],
                capture_output=True, text=True, check=False,
            )
    except (OSError, FileNotFoundError):
        # icacls unavailable — leave inherited ACL rather than risk lockout.
        pass

PUB_PEM = "OMNIX-AXIOM ML-DSA-65 PUBLIC KEY"
SEC_PEM = "OMNIX-AXIOM ML-DSA-65 SECRET KEY"
SIG_PEM = "OMNIX-AXIOM ML-DSA-65 SIGNATURE"


def _pem_wrap(kind: str, raw: bytes) -> str:
    b64 = base64.encodebytes(raw).decode("ascii")
    lines = [b64[i : i + 64] for i in range(0, len(b64), 64)]
    return (
        f"-----BEGIN {kind}-----\n"
        + "\n".join(lines)
        + f"\n-----END {kind}-----\n"
    )


def _pem_unwrap(pem: str, kind: str) -> bytes:
    m = f"-----BEGIN {kind}-----"
    n = f"-----END {kind}-----"
    if m not in pem or n not in pem:
        raise ValueError("invalid PEM")
    body = pem.split(m, 1)[1].split(n, 1)[0]
    s = "".join(line.strip() for line in body.splitlines() if line.strip())
    return base64.b64decode(s, validate=True)


def public_to_pem(pk: bytes) -> str:
    if len(pk) != P.PK_SIZE:
        raise ValueError("public key size")
    return _pem_wrap(PUB_PEM, pk)


def secret_to_pem(sk: bytes) -> str:
    if len(sk) != P.SK_SIZE:
        raise ValueError("secret key size")
    return _pem_wrap(SEC_PEM, sk)


def signature_to_pem(sig: bytes) -> str:
    if len(sig) != P.SIG_SIZE:
        raise ValueError("signature size")
    return _pem_wrap(SIG_PEM, sig)


def public_from_pem(pem: str) -> bytes:
    b = _pem_unwrap(pem, PUB_PEM)
    if len(b) != P.PK_SIZE:
        raise ValueError("decoded pk size")
    return b


def secret_from_pem(pem: str) -> bytes:
    b = _pem_unwrap(pem, SEC_PEM)
    if len(b) != P.SK_SIZE:
        raise ValueError("decoded sk size")
    return b


def signature_from_pem(pem: str) -> bytes:
    b = _pem_unwrap(pem, SIG_PEM)
    if len(b) != P.SIG_SIZE:
        raise ValueError("decoded sig size")
    return b


def write_keypair_dir(out: Path) -> None:
    """Write public.pem and secret.pem (mode 0o600) for current key in caller."""
    from . import keygen  # import after subsystems ready

    out = out.expanduser()
    out.mkdir(parents=True, exist_ok=True)
    pk, sk = keygen.keygen()
    p_pub = out / "public.pem"
    p_sec = out / "secret.pem"
    p_pub.write_text(public_to_pem(pk), encoding="ascii")
    # Encryption-at-rest (opt-in) for the secret; harden_permissions runs
    # inside write_secret. Lazy import avoids a keystore<->secure_keyfile cycle.
    from .secure_keyfile import write_secret

    write_secret(p_sec, secret_to_pem(sk))
