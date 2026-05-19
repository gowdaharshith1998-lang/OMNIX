from __future__ import annotations

import pytest

from omnix.runtime.cobol.sandbox import SandboxTimeoutError, run_command


def test_sandbox_timeout(tmp_path) -> None:
    with pytest.raises(SandboxTimeoutError):
        run_command(["python", "-c", "import time; time.sleep(2)"], cwd=tmp_path, timeout_s=0.1)
