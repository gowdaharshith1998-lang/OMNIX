"""Layer 4: adaptive example budgets (slice 17b round 2)."""

from __future__ import annotations

import ast
import logging
import subprocess
from pathlib import Path
from typing import Iterable

from omnix.scan.turboscan.types import BudgetEntry, BudgetPlan

_LOG = logging.getLogger("omnix.scan.turboscan.budget")


def _count_branches(node: ast.AST) -> int:
    n = 0
    for child in ast.walk(node):
        if isinstance(child, (ast.If, ast.For, ast.While, ast.Try, ast.Match)):
            n += 1
        elif isinstance(child, ast.BoolOp):
            n += len(child.values) - 1
    return n


def _cyclomatic_approx(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    base = 1 + _count_branches(node)
    return base


def _function_ast_metrics(
    tree: ast.Module, name: str
) -> tuple[int, int, int] | None:
    for n in tree.body:
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name:
            loc = n.end_lineno - n.lineno + 1 if n.end_lineno else len(n.body)
            branches = _count_branches(n)
            cyclo = _cyclomatic_approx(n)
            return loc, branches, cyclo
    return None


def analyze_python_function(path: Path, function_name: str) -> tuple[int, int, int]:
    try:
        src = path.read_text(encoding="utf-8", errors="replace")
        tree = ast.parse(src, filename=str(path))
    except (OSError, SyntaxError, ValueError) as e:
        _LOG.debug("budget_planner: parse failed for %s: %s", path, e)
        return 50, 0, 5
    m = _function_ast_metrics(tree, function_name)
    if m is None:
        return 50, 0, 5
    return m


def git_touched_last_24h(repo_root: Path, relpath: str) -> bool:
    try:
        r = subprocess.run(
            [
                "git",
                "-C",
                str(repo_root),
                "log",
                "-1",
                "--since=24.hours ago",
                "--",
                relpath,
            ],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as e:
        _LOG.debug("git recent check failed: %s", e)
        return False
    return r.returncode == 0 and bool((r.stdout or "").strip())


def examples_for_metrics(
    loc: int,
    branches: int,
    cyclomatic: int,
    *,
    recent_bonus: bool,
    trivial_cap: int = 25,
    default_cap: int = 100,
    complex_cap: int = 200,
) -> tuple[int, str]:
    trivial = (
        loc <= 3
        and branches == 0
        and cyclomatic <= 2
    )
    complex_ = loc > 50 or branches > 5 or cyclomatic > 10
    if trivial:
        tier = "trivial"
        ex = trivial_cap
    elif complex_:
        tier = "complex"
        ex = complex_cap
    else:
        tier = "default"
        ex = default_cap
    if recent_bonus:
        ex = int(ex * 1.5)
    return ex, tier


def build_budget_plan(
    repo_root: Path,
    targets: Iterable[tuple[str, str, int, Path]],
    *,
    worker_slots: int,
    examples_default: int = 100,
) -> BudgetPlan:
    """Compute per-function examples before dispatch (R4).

    ``targets`` yields ``(relpath, function_name, lineno, absolute_path)``.
    When parsing fails, uses ``examples_default``.
    """
    repo_root = repo_root.resolve()
    entries: list[BudgetEntry] = []
    total = 0
    for relp, fn, lineno, abs_path in targets:
        loc, br, cy = analyze_python_function(abs_path, fn)
        recent = git_touched_last_24h(repo_root, relp)
        ex, tier = examples_for_metrics(loc, br, cy, recent_bonus=recent)
        entries.append(
            BudgetEntry(
                relpath=relp,
                function_name=fn,
                lineno=lineno,
                examples=ex,
                tier=tier,
                recent_bonus=recent,
                loc=loc,
                branch_count=br,
            )
        )
        total += ex
    return BudgetPlan(
        entries=list(entries),
        budget_total=total,
        worker_slots=worker_slots,
    )
