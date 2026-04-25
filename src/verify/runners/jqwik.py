"""opt-in: JQwik / Maven (5b: detection only; execution defers to universal)."""

from __future__ import annotations

import shutil
from pathlib import Path

from .base import Layer6Result


def try_run_jqwik(project_root: Path) -> tuple[Layer6Result | None, str]:  # noqa: ARG001
    if not shutil.which("mvn"):
        return (None, "no_mvn")
    r = Layer6Result(
        findings=[],
        language="java",
        runner_used="jqwik",
        extra_metadata={"native": "deferred_to_universal", "ready": False},
    )
    return (r, "stub")
