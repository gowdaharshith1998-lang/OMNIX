from __future__ import annotations

from omnix.runtime.cobol.gnucobol_adapter import ProgramRun


def test_run_capture_shape() -> None:
    pr = ProgramRun(stdout=b"a", stderr=b"", returncode=0)
    assert pr.returncode == 0
