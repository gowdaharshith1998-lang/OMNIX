from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from omnix.graph.store import GraphStore
from omnix.parser.ingest_dispatch import ingest_unified_codebase
from omnix.rebuild.cobol_runner import iter_cobol_programs, rebuild_cobol_program
from omnix.runtime.cobol.capture import run_capture
from omnix.runtime.cobol.gnucobol_adapter import compile_cobol
from omnix.spec.cobol_hypothesis import generate_spec


def _has_llm_credentials() -> bool:
    return any(os.environ.get(name) for name in ("OMNIX_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GOOGLE_API_KEY"))


def test_cobol_rebuild_python_target_end_to_end(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    if shutil.which("cobc") is None:
        pytest.skip("cobc is required for real COBOL rebuild")
    if not _has_llm_credentials():
        pytest.skip("real LLM credentials are required for COBOL rebuild")

    monkeypatch.chdir(tmp_path)
    source = tmp_path / "HELLO.cob"
    source.write_text(
        """IDENTIFICATION DIVISION.
PROGRAM-ID. HELLO.
PROCEDURE DIVISION.
    DISPLAY "HELLO".
    STOP RUN.
""",
        encoding="utf-8",
    )
    fixtures = tmp_path / "fixtures" / "HELLO"
    fixtures.mkdir(parents=True)
    (fixtures / "input.bin").write_bytes(b"")
    exe = compile_cobol(source, out_dir=tmp_path / ".omnix" / "bin")
    run_capture(
        project_root=tmp_path,
        program=exe,
        fixtures_dir=tmp_path / "fixtures",
        output_root=tmp_path / ".omnix" / "captures" / "cobol" / "HELLO",
    )
    generate_spec("HELLO", tmp_path / ".omnix" / "captures" / "cobol", tmp_path / "tests" / "cobol" / "generated")

    db_dir = tmp_path / ".omnix"
    db_dir.mkdir(exist_ok=True)
    store = GraphStore(str(db_dir / "omnix.db"))
    ingest_unified_codebase(str(tmp_path), store)
    programs = iter_cobol_programs(store, tmp_path, node_filter="*HELLO*")

    receipt = rebuild_cobol_program(
        store=store,
        program_node_id=programs[0].node_id,
        target_language="python",
        receipts_dir=tmp_path / ".omnix" / "receipts" / "cobol",
        project_path=tmp_path,
    )

    assert receipt.is_file()
    assert (receipt.parent / "HELLO.py").is_file()
    store.close()
