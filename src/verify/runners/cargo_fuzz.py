"""opt-in: ``cargo fuzz`` (ITER 5b: stub — native pipeline not yet wired; returns defer)."""

from __future__ import annotations

import shutil
from pathlib import Path

from .base import Layer6Result


def try_run_cargo_fuzz(  # noqa: ARG001
    project_root: Path,
) -> tuple[Layer6Result | None, str]:
    """
    If ``cargo`` is missing, native is unavailable. Otherwise 5b leaves execution
    to the subprocess+LLM floor; return (None, reason) to mean *defer*.
    """
    if not shutil.which("cargo"):
        return (None, "no_cargo")
    r = Layer6Result(
        findings=[],
        language="rust",
        runner_used="cargo_fuzz",
        extra_metadata={"native": "deferred_to_universal", "ready": False},
    )
    return (r, "stub")
