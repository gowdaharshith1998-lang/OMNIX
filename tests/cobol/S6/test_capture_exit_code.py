from __future__ import annotations

import json
from pathlib import Path

from omnix.runtime.cobol.capture import ProgramRun, run_capture


def _runner(_program: Path, _stdin: bytes, _cwd: Path, _timeout: float) -> ProgramRun:
    return ProgramRun(stdout=b"", stderr=b"", returncode=7)


def test_capture_exit_code(tmp_path: Path) -> None:
    fx = tmp_path / "fx" / "fixture1"
    fx.mkdir(parents=True)
    (fx / "input.bin").write_bytes(b"abc")
    prog = tmp_path / "prog"
    prog.write_text("", encoding="utf-8")
    out = tmp_path / "out"
    run_capture(project_root=tmp_path, program=prog, fixtures_dir=tmp_path / "fx", output_root=out, runner=_runner)
    payload = json.loads((out / "fixture1.json").read_text(encoding="utf-8"))
    assert payload["exit_code"] == 7
