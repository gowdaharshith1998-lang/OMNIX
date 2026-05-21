from __future__ import annotations

from click.testing import CliRunner

from omnix.cli import main
from omnix.graph.store import GraphStore


def test_enrich_cli_uses_project_omnix_db(tmp_path) -> None:
    (tmp_path / ".omnix").mkdir()
    store = GraphStore(str(tmp_path / ".omnix" / "omnix.db"))
    store.add_node(
        "prog:HELLO",
        "HELLO",
        "CobolProgram",
        metadata={"source_text": "IDENTIFICATION DIVISION.\nPROGRAM-ID. HELLO."},
    )
    store.commit()
    store.close()
    runner = CliRunner()
    result = runner.invoke(main, ["cobol", "enrich", str(tmp_path), "--passes", "1"])
    assert result.exit_code == 0, result.output
    assert "mock_calls=" in result.output


def test_skills_list_empty_bank(tmp_path) -> None:
    (tmp_path / ".omnix").mkdir()
    store = GraphStore(str(tmp_path / ".omnix" / "omnix.db"))
    store.add_node("prog:HELLO", "HELLO", "CobolProgram", metadata={"source_text": "x"})
    store.commit()
    store.close()
    result = CliRunner().invoke(main, ["cobol", "skills", "list", str(tmp_path)])
    assert result.exit_code == 0, result.output
    assert "No COBOL GraphRAG skills" in result.output
