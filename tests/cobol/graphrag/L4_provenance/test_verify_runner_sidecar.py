from __future__ import annotations

from omnix.provenance.sidecar import write_sidecar
from omnix.provenance.signer import SidecarSigner
from omnix.verify.runner import verify_sidecar


def test_verify_sidecar_reports_independent_result(tmp_path) -> None:
    signer = SidecarSigner(tmp_path)
    sidecar, sig = write_sidecar(
        tmp_path,
        "HELLO",
        {"schema_version": "omnix.provenance.v1", "target_program_id": "HELLO"},
        signer,
    )
    result = verify_sidecar(sidecar, sig, tmp_path / ".omnix" / "pubkey.pem")
    assert result.ok
