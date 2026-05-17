"""
Detect which test command to run inside a **sandbox** copy of the project.
Priority: pytest > cargo > go > mvn > npm > dotnet (documented in ``order_chosen``).
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(frozen=True)
class TestRunnerSpec:
    """What to run in the sandbox ``cwd``."""

    runner_id: str
    """``pytest`` | ``cargo`` | ``go`` | ``mvn`` | ``npm`` | ``dotnet`` | ``none``"""

    command: list[str]
    order_chosen: list[str] = field(default_factory=list)
    """Priority labels tried in order."""


def _has(p: Path) -> bool:
    return p.is_file()


def detect_test_runner(sandbox_root: Path) -> TestRunnerSpec:
    """
    Inspect *sandbox_root* only (mirrored project). Returns the first match
    in priority order; ``order_chosen`` lists the decision path.
    """
    root = sandbox_root.resolve()
    order: list[str] = []
    if _has(root / "pyproject.toml") or _has(root / "pytest.ini") or _has(
        root / "tox.ini"
    ) or _has(root / "setup.cfg"):
        order.append("pytest")
        return TestRunnerSpec(
            "pytest",
            [__import__("sys").executable, "-m", "pytest", "-q", "--tb=no"],
            order_chosen=order,
        )
    if _has(root / "Cargo.toml"):
        order.append("cargo")
        return TestRunnerSpec("cargo", ["cargo", "test", "--", "--nocapture"], order_chosen=order)  # noqa: E501
    if _has(root / "go.mod"):
        order.append("go")
        return TestRunnerSpec("go", ["go", "test", "./..."], order_chosen=order)
    if _has(root / "pom.xml"):
        order.append("mvn")
        return TestRunnerSpec("mvn", ["mvn", "-q", "test"], order_chosen=order)
    if _has(root / "package.json"):
        try:
            raw = (root / "package.json").read_text(encoding="utf-8", errors="replace")
            j = json.loads(raw)
            if isinstance(j, dict) and isinstance(j.get("scripts"), dict) and "test" in j["scripts"]:  # noqa: E501, SIM102
                order.append("npm")
                return TestRunnerSpec("npm", ["npm", "test"], order_chosen=order)
        except (OSError, json.JSONDecodeError, TypeError, KeyError):
            pass
    for cs in root.glob("*.csproj"):
        if cs.is_file():
            order.append("dotnet")
            return TestRunnerSpec("dotnet", ["dotnet", "test", str(cs.name)], order_chosen=order)  # noqa: E501
    return TestRunnerSpec("none", [], order_chosen=order or ["(none)"])


def parse_pytest_summary(stdout: str, stderr: str) -> tuple[int, int]:
    """Best-effort ``N passed`` / ``M failed`` from *pytest* output."""
    t = f"{stdout}\n{stderr}"
    passed = 0
    failed = 0
    m = re.search(r"(\d+)\s+passed", t, re.I)
    if m:
        passed = int(m.group(1))
    m2 = re.search(r"(\d+)\s+failed", t, re.I)
    if m2:
        failed = int(m2.group(1))
    tot = passed + failed
    if tot == 0 and "passed" in t.lower():
        passed = 1
        tot = 1
    return passed, max(tot, passed + failed)
