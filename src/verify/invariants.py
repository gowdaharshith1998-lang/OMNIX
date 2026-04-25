"""Consecutive call-site invariant pairs (e.g. encode / decode, push / pop)."""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

from .boundary import _callee_name as callee_name

_CACHE: dict[Path, ast.Module] = {}


def function_names_in_file(p: Path | str) -> set[str]:
    if isinstance(p, str):
        p = Path(p)
    mod = _parse(p)
    return {n.name for n in ast.walk(mod) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def _parse(p: Path) -> ast.Module:
    a = p.resolve()
    if a in _CACHE:
        return _CACHE[a]
    t = ast.parse(a.read_text(encoding="utf-8"), filename=str(a))
    assert isinstance(t, ast.Module)
    _CACHE[a] = t
    return t


def detect_invariant_pairs_in_file(
    path: Path | str,
    allowed_names: set[str] | None = None,
    *,
    file_scope_path: Path | str | None = None,
    module_paths_considered: set[Path] | None = None,
) -> list[tuple[str, str]]:
    p = Path(path) if not isinstance(path, Path) else path
    _ = file_scope_path, module_paths_considered
    al = allowed_names or function_names_in_file(p)
    mod = _parse(p)
    return _find_pairs_in_module(mod, al)


def _find_pairs_in_module(mod: ast.Module, allowed: set[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for fn in ast.walk(mod):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        stm = fn.body
        for i in range(len(stm) - 1):
            a, b2 = stm[i], stm[i + 1]
            f2, g, mid = _sequential_dataflow_pair(a, b2)
            if f2 and g and mid:
                if f2 in allowed and g in allowed:
                    out.append((f2, g))
    return out


def _sequential_dataflow_pair(
    a: ast.stmt, b2: ast.stmt
) -> tuple[str | None, str | None, str | None]:
    """a: y = f(x);  b2:  ...  g(y)  with y binding."""
    f2: str | None = None
    mid: str | None = None
    yname: str | None = None
    if isinstance(a, ast.Assign) and len(a.targets) == 1 and isinstance(
        a.targets[0], ast.Name
    ):
        yname = a.targets[0].id
        if isinstance(a.value, ast.Call):
            f2 = callee_name(a.value)
    if f2 is None or yname is None:
        return (None, None, None)
    ncall: ast.Call | None = None
    if isinstance(b2, ast.Assign) and isinstance(b2.value, ast.Call):
        ncall = b2.value
    elif isinstance(b2, ast.Expr) and isinstance(b2.value, ast.Call):
        ncall = b2.value
    elif isinstance(b2, ast.Return) and isinstance(b2.value, ast.Call):
        ncall = b2.value
    if ncall is None:
        return (f2, None, yname)
    g = callee_name(ncall)
    for arg in ncall.args + list(ncall.keywords):
        argv = arg.value if isinstance(arg, ast.keyword) else arg
        if isinstance(argv, ast.Name) and argv.id == yname:
            if g:
                return (f2, g, yname)
    return (f2, None, yname)


# Clear cache for tests
def clear_invariant_cache() -> None:
    _CACHE.clear()
