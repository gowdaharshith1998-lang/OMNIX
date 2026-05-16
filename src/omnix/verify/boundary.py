"""Literal argument extraction and ≥2-caller boundary filtering."""

from __future__ import annotations

import ast
from collections import defaultdict
from typing import Any, Iterable


def extract_literal_args_for_call(
    call: ast.Call, _full_name: str, *, short_name: str
) -> dict[int, list[Any]]:
    """Map positional index -> values for ast.Constant arguments only."""
    cname = _callee_name(call)
    if cname != short_name:
        return {}
    out: dict[int, list[Any]] = {}
    for i, arg in enumerate(call.args):
        v: Any
        if isinstance(arg, ast.Constant):
            v = arg.value
        elif (
            isinstance(arg, ast.UnaryOp)
            and isinstance(arg.op, ast.USub)
            and isinstance(arg.operand, ast.Constant)
        ):
            x = arg.operand.value
            v = -x if isinstance(x, (int, float, complex)) else 0
        else:
            continue
        if isinstance(v, (int, str, bool, type(None), float, bytes)):
            out.setdefault(i, []).append(v)
    return out


def _callee_name(call: ast.Call) -> str:
    f = call.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        if isinstance(f.value, ast.Name) and f.value.id in ("self", "cls"):
            return f.attr
        return f.attr
    return ""


def aggregate_boundaries(
    site_tuples: Iterable[tuple[dict[int, list[Any]], str]]
) -> dict[tuple[int, Any], set[str]]:
    """
    (pos, value) -> set of distinct caller keys that have that literal
    in at least one call. Values deduped per call site (set of literals in one call).
    """
    acc: dict[tuple[int, Any], set[str]] = defaultdict(set)
    for site, ck in site_tuples:
        for pos, vals in site.items():
            for v in set(vals):
                acc[(pos, v)].add(ck)
    return dict(acc)


def filter_frequent_literals(
    merged: dict[tuple[int, Any], set[str]],
    *,
    min_distinct_callers: int = 2,
) -> dict[int, list[Any]]:
    out: dict[int, list[Any]] = {}
    for (pos, v), cks in merged.items():
        if len(cks) >= min_distinct_callers:
            out.setdefault(pos, []).append(v)
    return {k: sorted(v, key=lambda x: (type(x).__name__, str(x))) for k, v in out.items() if v}
