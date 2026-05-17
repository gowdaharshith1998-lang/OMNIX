"""Select native or universal subprocess runner for a target (runtime ``shutil.which``)."""

from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

Backend = Literal["cargo_fuzz", "go_fuzz", "jqwik", "subprocess_llm", "python_native"]


@dataclass(frozen=True)
class Detection:
    """Describes the chosen backend and why native may be skipped."""

    backend: Backend
    native_eligible: bool
    reason: str
    log: dict[str, Any] = field(default_factory=dict)


def _has(root: Path, *parts: str) -> bool:
    return (root.joinpath(*parts)).is_file()


def detect_universal_backend(
    project_root: Path, rel_file: str, file_path: Path, language_guess: str
) -> Detection:
    """
    If native tools + manifest exist, *prefer* a native label; the runner still
    may fall back to the subprocess+LLM floor. Python uses ``python_native`` only
    when the caller is wiring ``.py`` (this module is for non-Python & routing).
    """
    root = project_root.resolve()
    lg = (language_guess or "").lower()
    log: dict[str, Any] = {"language_guess": language_guess}
    if rel_file.lower().endswith(".py") or "python" in lg:
        return Detection("python_native", True, "python file", {**log, "note": "p11_python_path"})  # noqa: E501
    if _has(root, "Cargo.toml") and file_path.suffix in (".rs",) and shutil.which("cargo"):
        log["cargo_fuzz"] = "candidate"
        return Detection("cargo_fuzz", True, "rust+cargo", log)
    if _has(root, "go.mod") and file_path.suffix == ".go" and shutil.which("go"):
        log["go_fuzz"] = "candidate"
        return Detection("go_fuzz", True, "go+go.mod", log)
    if _has(root, "pom.xml") and file_path.suffix in (".java", ".kt") and shutil.which("mvn"):
        log["jqwik"] = "candidate"
        return Detection("jqwik", True, "java/maven", log)
    return Detection("subprocess_llm", True, "universal_floor", log)
