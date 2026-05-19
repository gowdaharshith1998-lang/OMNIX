from __future__ import annotations

from pathlib import Path

from omnix.runtime.cobol.capture import ProgramRun, run_capture


def _runner(_program: Path, stdin_bytes: bytes, _cwd: Path, _timeout: float) -> ProgramRun:
    return ProgramRun(stdout=stdin_bytes.upper(), stderr=b"", returncode=0)


def test_capture_stdin_stdout(tmp_path: Path) -> None:
    fx = tmp_path / "fx" / "fixture1"
    fx.mkdir(parents=True)
    (fx / "input.bin").write_bytes(b"abc")
    out = tmp_path / "out"
    prog = tmp_path / "prog"
    prog.write_text("", encoding="utf-8")
    got = run_capture(project_root=tmp_path, program=prog, fixtures_dir=tmp_path / "fx", output_root=out, runner=_runner)
    assert len(got) == 1
