"""Typed structures for TURBOSCAN (slice 17b round 2)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class BudgetEntry:
    """Per-function example budget after Layer 4."""

    relpath: str
    function_name: str
    lineno: int
    examples: int
    tier: str  # trivial | default | complex
    recent_bonus: bool
    loc: int
    branch_count: int


@dataclass
class BudgetPlan:
    """Full scan budget plan (R4, R12)."""

    entries: list[BudgetEntry]
    budget_total: int  # sum of planned examples
    worker_slots: int

    def by_function_key(self) -> dict[tuple[str, str], int]:
        return {(e.relpath, e.function_name): e.examples for e in self.entries}


@dataclass
class TurboFindingView:
    """Normalized finding for R9 comparison (function × bug class)."""

    function_name: str
    bug_class: str
    raw: dict[str, Any]


@dataclass
class TurboScanResult:
    """Public result object from ``scan()``."""

    findings: list[TurboFindingView]
    scan_completed_successfully: bool
    wall_clock_seconds: float
    files_scanned: list[str]
    budget_plan: BudgetPlan | None
    budget_used: int
    scan_phase: str
    wall_clock_ms: int
    hygiene_events: list[dict[str, Any]] = field(default_factory=list)
    plan_only: bool = False


def finding_bug_class(row: dict[str, Any]) -> str:
    dim = str(row.get("dimension") or "")
    if dim == "filesystem_hygiene":
        return "filesystem_hygiene"
    kind = str(row.get("kind") or "")
    if kind:
        return kind
    return "pbt_failure"


def raw_findings_to_views(rows: list[dict[str, Any]]) -> list[TurboFindingView]:
    out: list[TurboFindingView] = []
    for r in rows:
        fn = str(r.get("function") or "")
        out.append(
            TurboFindingView(
                function_name=fn,
                bug_class=finding_bug_class(r),
                raw=dict(r),
            )
        )
    return out


def turboscan_state_dir(repo_root: Path) -> Path:
    return (repo_root.resolve() / ".omnix" / "turboscan").resolve()


def turboscan_last_scan_path(repo_root: Path) -> Path:
    return turboscan_state_dir(repo_root) / "last_green_scan.json"
