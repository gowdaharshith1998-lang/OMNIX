from __future__ import annotations

import zipfile
from pathlib import Path

import pytest

from tests.cobol.orchestrator.helpers import write_receipt


def test_audit_export_zip_shape_and_verify_script(tmp_path: Path) -> None:
    from omnix.orchestrator.cobol.audit_export import export_audit_zip
    from omnix.orchestrator.cobol.discovery import DiscoveredProgram
    from omnix.orchestrator.cobol.run_state import RunState

    state = RunState.create(tmp_path, "python", 1.0)
    state.add_program(DiscoveredProgram("HELLO", tmp_path / "HELLO.cob", [], [], None))
    receipt = state.run_dir / "receipts" / "HELLO.json"
    write_receipt(receipt)
    state.transition("HELLO", "verified", receipt_path=str(receipt))

    out = export_audit_zip(run_state=state, out_path=tmp_path / "audit.zip")

    with zipfile.ZipFile(out) as zf:
        assert {"README.md", "verify.py", "run_summary.json", "receipts/HELLO.json", "receipts/HELLO.sig", "replicas/HELLO.py"} <= set(zf.namelist())
    state.close()


def test_audit_export_empty_run_fails(tmp_path: Path) -> None:
    from omnix.orchestrator.cobol.audit_export import export_audit_zip
    from omnix.orchestrator.cobol.run_state import RunState

    state = RunState.create(tmp_path, "python", 1.0)
    with pytest.raises(ValueError, match="no verified receipts"):
        export_audit_zip(run_state=state, out_path=tmp_path / "audit.zip")
    state.close()

