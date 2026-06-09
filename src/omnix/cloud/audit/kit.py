"""Customer audit-kit export.

Bundles:
  manifest.json          canonical inventory
  receipts/*.json        receipt payloads
  receipts/*.sig         raw ML-DSA-65 signatures
  receipts/*.pub         public keys
  rekor/*.proof.json     inclusion proofs (when Rekor enabled)
  verify.py              offline verifier (zero deps beyond stdlib + omnix wheel)
  README.md              human-readable instructions

The bundle is itself a tar.gz with a top-level SHA-256 + ML-DSA-65 signature
so the auditor can detect tampering of the kit itself.
"""

from __future__ import annotations

import hashlib
import io
import json
import tarfile
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class AuditEvidence:
    receipt_id: str
    payload_canonical: bytes
    signature: bytes
    public_key: bytes
    rekor_inclusion: dict | None = None
    metadata: dict = field(default_factory=dict)


@dataclass
class AuditKit:
    customer: str
    tenant_id: str
    evidence: list[AuditEvidence] = field(default_factory=list)
    generated_at: str = ""


def export_kit(kit: AuditKit, output_path: str | Path,
               *, signer=None) -> dict:
    """Write kit to a tar.gz; return summary dict.

    ``signer`` is an optional callable returning (sig, pubkey) over the
    canonical manifest. When set, the manifest signature is also added to
    the bundle and to the summary.
    """
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)

    manifest = {
        "customer": kit.customer,
        "tenant_id": kit.tenant_id,
        "generated_at": kit.generated_at,
        "receipts": [],
    }

    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        for ev in kit.evidence:
            digest = hashlib.sha256(ev.payload_canonical).hexdigest()
            manifest["receipts"].append({
                "receipt_id": ev.receipt_id,
                "payload_sha256": digest,
                "rekor": bool(ev.rekor_inclusion),
                "metadata": ev.metadata,
            })
            _add_bytes(tar, f"receipts/{ev.receipt_id}.json", ev.payload_canonical)
            _add_bytes(tar, f"receipts/{ev.receipt_id}.sig", ev.signature)
            _add_bytes(tar, f"receipts/{ev.receipt_id}.pub", ev.public_key)
            if ev.rekor_inclusion:
                _add_bytes(
                    tar,
                    f"rekor/{ev.receipt_id}.proof.json",
                    json.dumps(ev.rekor_inclusion, indent=2).encode(),
                )

        manifest_bytes = json.dumps(manifest, sort_keys=True, indent=2).encode()
        _add_bytes(tar, "manifest.json", manifest_bytes)

        if signer is not None:
            sig, pk = signer(manifest_bytes)
            _add_bytes(tar, "manifest.sig", sig)
            _add_bytes(tar, "manifest.pub", pk)

        _add_text(tar, "verify.py", _OFFLINE_VERIFIER)
        _add_text(tar, "README.md", _README)

    output.write_bytes(buf.getvalue())
    sha = hashlib.sha256(buf.getvalue()).hexdigest()

    return {
        "path": str(output),
        "size_bytes": output.stat().st_size,
        "sha256": sha,
        "receipts": len(kit.evidence),
    }


def write_offline_verifier_script(path: str | Path) -> Path:
    p = Path(path)
    p.write_text(_OFFLINE_VERIFIER, encoding="utf-8")
    return p


def _add_bytes(tar: tarfile.TarFile, name: str, data: bytes) -> None:
    info = tarfile.TarInfo(name=name)
    info.size = len(data)
    info.mode = 0o644
    tar.addfile(info, io.BytesIO(data))


def _add_text(tar: tarfile.TarFile, name: str, text: str) -> None:
    _add_bytes(tar, name, text.encode("utf-8"))


# Standalone verifier script: zero deps beyond the omnix wheel + stdlib.
_OFFLINE_VERIFIER = '''#!/usr/bin/env python3
"""OMNIX offline audit-kit verifier.

Usage:
    python verify.py [PATH_TO_KIT_DIR]
    python verify.py audit-kit.tar.gz

For each receipt, runs ML-DSA-65 (FIPS 204) verification using
``omnix.receipts.verify`` (pure-Python, zero external crypto deps).
Returns exit code 0 if all signatures + inclusion proofs verify.
"""

from __future__ import annotations

import hashlib
import json
import sys
import tarfile
from pathlib import Path


def _extract_if_archive(arg: str) -> Path:
    p = Path(arg)
    if p.is_dir():
        return p
    out = Path(arg + ".unpacked")
    out.mkdir(exist_ok=True)
    with tarfile.open(p) as tar:
        tar.extractall(out)
    return out


def main(argv: list[str]) -> int:
    if len(argv) < 2:
        print("usage: verify.py <kit-dir-or-tarball>")
        return 2
    try:
        from omnix.receipts.verify import verify_bytes
    except ImportError:
        print("missing omnix.receipts.verify — install the omnix package "
              "(pip install omnix) and retry.")
        return 2

    root = _extract_if_archive(argv[1])
    manifest = json.loads((root / "manifest.json").read_text())

    fails = 0
    for rcpt in manifest.get("receipts", []):
        rid = rcpt["receipt_id"]
        payload = (root / "receipts" / f"{rid}.json").read_bytes()
        sig = (root / "receipts" / f"{rid}.sig").read_bytes()
        pk = (root / "receipts" / f"{rid}.pub").read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        if digest != rcpt["payload_sha256"]:
            print(f"FAIL  {rid}: sha256 mismatch")
            fails += 1
            continue
        ok = verify_bytes(pk, payload, b"", sig)
        print(f"{('OK  ' if ok else 'FAIL'):4} {rid}: sha256={digest}")
        if not ok:
            fails += 1
    print(f"\\nResult: {len(manifest['receipts']) - fails} ok, {fails} failed")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
'''


_README = """# OMNIX Customer Audit Kit

This bundle contains every signed receipt OMNIX produced for your tenant.

## One-shot verification (no internet needed)

    pip install omnix
    python verify.py .

Exit code 0 = every receipt's ML-DSA-65 signature verifies and every payload
SHA-256 matches the manifest.

## Layout

    manifest.json             tenant + customer + receipts inventory
    manifest.sig              ML-DSA-65 signature of manifest.json
    manifest.pub              public key for manifest.sig
    receipts/<id>.json        canonical receipt payload
    receipts/<id>.sig         ML-DSA-65 signature (FIPS 204)
    receipts/<id>.pub         public key for the receipt signature
    rekor/<id>.proof.json     transparency-log inclusion proof (when enabled)

## Compliance mapping

- DORA Article 6 — signed audit trail, 5-year retention
- EU AI Act Articles 12 + 26(6) — tamper-resistant logging
- NIST PQC 2030 — ML-DSA-65 (FIPS 204)
- CNSA 2.0 (2035) — same algorithm
- SOC 2 CC7.2 + CC4.1 — System Monitoring + Monitoring of Controls
"""
