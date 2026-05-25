"""End-to-end audit-kit export + offline verification."""

from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import tarfile

import pytest

from omnix.cloud.audit.kit import (
    AuditEvidence,
    AuditKit,
    export_kit,
)


@pytest.fixture
def real_signed_evidence():
    keygen = pytest.importorskip("omnix.receipts.keygen")
    sign_mod = pytest.importorskip("omnix.receipts.sign")
    evidence = []
    for i in range(3):
        pk, sk = keygen.keygen()
        payload = json.dumps({"receipt_id": f"r-{i}", "kind": "replication"},
                             sort_keys=True, separators=(",", ":")).encode()
        sig = sign_mod.sign_bytes(sk, payload, b"", None)
        evidence.append(
            AuditEvidence(
                receipt_id=f"r-{i}",
                payload_canonical=payload,
                signature=sig,
                public_key=pk,
                metadata={"target": "java21"},
            )
        )
    return evidence


def test_export_kit_creates_tarball_and_inventory(real_signed_evidence, tmp_path):
    kit = AuditKit(customer="Bank Acme", tenant_id="org-bank-acme",
                   evidence=real_signed_evidence, generated_at="2026-05-25T00:00Z")
    out = tmp_path / "audit-kit.tar.gz"
    summary = export_kit(kit, out)
    assert out.exists()
    assert summary["receipts"] == 3
    with tarfile.open(out) as tar:
        names = tar.getnames()
        assert "manifest.json" in names
        for i in range(3):
            assert f"receipts/r-{i}.json" in names
            assert f"receipts/r-{i}.sig" in names
            assert f"receipts/r-{i}.pub" in names
        assert "verify.py" in names
        assert "README.md" in names


def test_offline_verifier_script_validates_real_kit(real_signed_evidence, tmp_path):
    """Run the bundled verify.py script in a subprocess against the unpacked kit."""
    kit = AuditKit(customer="Bank Acme", tenant_id="org-bank-acme",
                   evidence=real_signed_evidence)
    out = tmp_path / "audit-kit.tar.gz"
    export_kit(kit, out)

    # Unpack
    unpack = tmp_path / "unpack"
    unpack.mkdir()
    with tarfile.open(out) as tar:
        tar.extractall(unpack)

    # Run the verifier script
    proc = subprocess.run(
        [sys.executable, str(unpack / "verify.py"), str(unpack)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, f"stderr:\n{proc.stderr}\nstdout:\n{proc.stdout}"
    assert "3 ok, 0 failed" in proc.stdout


def test_offline_verifier_catches_tampered_payload(real_signed_evidence, tmp_path):
    kit = AuditKit(customer="Bank", tenant_id="t", evidence=real_signed_evidence)
    out = tmp_path / "audit-kit.tar.gz"
    export_kit(kit, out)
    unpack = tmp_path / "unpack"
    unpack.mkdir()
    with tarfile.open(out) as tar:
        tar.extractall(unpack)

    # Tamper with one receipt's payload
    target = unpack / "receipts" / "r-1.json"
    target.write_bytes(target.read_bytes().replace(b"replication", b"tampered---"))

    proc = subprocess.run(
        [sys.executable, str(unpack / "verify.py"), str(unpack)],
        capture_output=True, text=True,
    )
    assert proc.returncode == 1
    assert "FAIL" in proc.stdout


def test_kit_manifest_is_signed(real_signed_evidence, tmp_path):
    from omnix.receipts import keygen, sign as sign_mod

    pk, sk = keygen.keygen()

    def manifest_signer(msg: bytes) -> tuple[bytes, bytes]:
        return sign_mod.sign_bytes(sk, msg, b"", None), pk

    kit = AuditKit(customer="Bank", tenant_id="t", evidence=real_signed_evidence)
    out = tmp_path / "audit-kit.tar.gz"
    export_kit(kit, out, signer=manifest_signer)

    unpack = tmp_path / "unpack"
    unpack.mkdir()
    with tarfile.open(out) as tar:
        tar.extractall(unpack)

    manifest = (unpack / "manifest.json").read_bytes()
    sig = (unpack / "manifest.sig").read_bytes()
    pubkey = (unpack / "manifest.pub").read_bytes()
    from omnix.receipts.verify import verify_bytes
    assert verify_bytes(pubkey, manifest, b"", sig)
