from __future__ import annotations

from pathlib import Path

from tests.cobol.orchestrator.helpers import write_program


def test_discovery_finds_all_cobol_extensions_and_program_ids(tmp_path: Path) -> None:
    from omnix.orchestrator.cobol.discovery import discover

    for name, suffix in (("ALPHA", ".cob"), ("BETA", ".cbl"), ("GAMMA", ".cobol")):
        p = write_program(tmp_path, name)
        p.rename(tmp_path / f"{name}{suffix}")

    found = discover(tmp_path)

    assert [p.program_id for p in found.programs] == ["ALPHA", "BETA", "GAMMA"]


def test_discovery_finds_copybooks_and_orphans(tmp_path: Path) -> None:
    from omnix.orchestrator.cobol.discovery import discover

    copybooks = tmp_path / "copybooks"
    copybooks.mkdir()
    used = copybooks / "CUSTREC.cpy"
    used.write_text("01 CUSTREC PIC X(10).\n", encoding="utf-8")
    orphan = copybooks / "UNUSED.cpy"
    orphan.write_text("01 UNUSED PIC X.\n", encoding="utf-8")
    write_program(tmp_path, "HELLO", copy="CUSTREC")

    found = discover(tmp_path)

    assert found.programs[0].copybook_paths == [used]
    assert found.orphan_copybooks == [orphan]


def test_discovery_finds_fixtures_and_flags_missing(tmp_path: Path) -> None:
    from omnix.orchestrator.cobol.discovery import discover

    write_program(tmp_path, "WITHFX")
    write_program(tmp_path, "NOFX")
    inputs = tmp_path / "inputs"
    inputs.mkdir()
    fixture = inputs / "WITHFX.in"
    fixture.write_bytes(b"abc")

    found = discover(tmp_path)
    by_id = {p.program_id: p for p in found.programs}

    assert by_id["WITHFX"].fixture_paths == [fixture]
    assert by_id["NOFX"].fixture_paths == []


def test_discovery_excludes_nested_repos_and_cache_dirs(tmp_path: Path) -> None:
    from omnix.orchestrator.cobol.discovery import discover

    write_program(tmp_path, "ROOT")
    for excluded in (".git", ".omnix", "__pycache__", "node_modules"):
        nested = tmp_path / excluded
        nested.mkdir()
        write_program(nested, "HIDDEN")

    found = discover(tmp_path)

    assert [p.program_id for p in found.programs] == ["ROOT"]

