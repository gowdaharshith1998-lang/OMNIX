"""opt-in: ``go test -fuzz`` (5b: stub; defer to universal floor)."""

from __future__ import annotations

import shutil
from pathlib import Path

from .base import Layer6Result


def try_run_go_fuzz(project_root: Path) -> tuple[Layer6Result | None, str]:  # noqa: ARG001
    if not shutil.which("go"):
        return (None, "no_go")
    r = Layer6Result(
        findings=[],
        language="go",
        runner_used="go_fuzz",
        extra_metadata={"native": "deferred_to_universal", "ready": False},
    )
    return (r, "stub")
