from __future__ import annotations

import subprocess
import zipfile

from omnix.provenance.sidecar import write_sidecar
from omnix.provenance.signer import SidecarSigner


def test_audit_zip_verify_script_handles_sidecars(tmp_path) -> None:
    from omnix.orchestrator.cobol.audit_export import _verify_script

    receipts = tmp_path / "receipts"
    receipts.mkdir()
    signer = SidecarSigner(tmp_path)
    payload = {
        "gate_results": [
            {"gate_number": n, "gate_name": str(n), "status": "passed", "details": {}}
            for n in range(1, 7)
        ]
    }
    receipt = receipts / "HELLO.json"
    receipt.write_text(__import__("json").dumps(payload), encoding="utf-8")
    sig = signer.sign_b64({"gate_results": sorted(payload["gate_results"], key=lambda g: g["gate_number"])})
    receipt.with_suffix(".sig").write_text(sig, encoding="utf-8")
    write_sidecar(receipts, "HELLO", {"schema_version": "omnix.provenance.v1", "target_program_id": "HELLO"}, signer)
    (tmp_path / "public_key.pem").write_bytes((tmp_path / ".omnix" / "pubkey.pem").read_bytes())
    (tmp_path / "verify.py").write_text(_verify_script(), encoding="utf-8")
    result = subprocess.run(["python", "verify.py"], cwd=tmp_path, text=True, capture_output=True, check=False)
    assert result.returncode == 0, result.stderr + result.stdout
