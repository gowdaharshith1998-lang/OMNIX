from __future__ import annotations

from pathlib import Path

from omnix.runtime.cobol.capture import run_capture


def test_capture_missing_fixture(tmp_path: Path) -> None:
    fx = tmp_path / "fx"
    fx.mkdir()
    prog = tmp_path / "prog"
    prog.write_text("", encoding="utf-8")
    out = tmp_path / "out"
    got = run_capture(project_root=tmp_path, program=prog, fixtures_dir=fx, output_root=out)
    assert got == []
