from __future__ import annotations

import zipfile

from omnix.provenance.sidecar import write_sidecar
from omnix.provenance.signer import SidecarSigner
from tests.cobol.orchestrator.helpers import write_receipt


def test_audit_export_includes_sidecar(tmp_path) -> None:
    from omnix.orchestrator.cobol.audit_export import export_audit_zip
    from omnix.orchestrator.cobol.discovery import DiscoveredProgram
    from omnix.orchestrator.cobol.run_state import RunState

    state = RunState.create(tmp_path, "python", 1.0)
    state.add_program(DiscoveredProgram("HELLO", tmp_path / "HELLO.cob", [], [], None))
    receipt = state.run_dir / "receipts" / "HELLO.json"
    write_receipt(receipt)
    write_sidecar(
        receipt.parent,
        "HELLO",
        {"schema_version": "omnix.provenance.v1", "target_program_id": "HELLO"},
        SidecarSigner(tmp_path),
    )
    state.transition("HELLO", "verified", receipt_path=str(receipt))
    try:
        out = export_audit_zip(run_state=state, out_path=tmp_path / "audit.zip")
        with zipfile.ZipFile(out) as zf:
            names = set(zf.namelist())
        assert "receipts/HELLO.provenance.json" in names
        assert "receipts/HELLO.provenance.sig" in names
    finally:
        state.close()
