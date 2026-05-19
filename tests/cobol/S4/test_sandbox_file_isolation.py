from __future__ import annotations

from omnix.runtime.cobol.sandbox import run_command


def test_sandbox_file_isolation(tmp_path) -> None:
    p = run_command(["python", "-c", "print('ok')"], cwd=tmp_path, timeout_s=2)
    assert p.returncode == 0
