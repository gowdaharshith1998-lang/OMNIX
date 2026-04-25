"""Heuristic detection of public entry points (``__main__``, web/CLI shims, argparse)."""

from __future__ import annotations

import ast
import os
import sys
from pathlib import Path
from typing import TypeGuard


def _relpos(file_path: Path, root: Path) -> str:
    try:
        return file_path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return file_path.name


def _is_name(n: ast.expr) -> bool:
    return isinstance(n, ast.Name)


def _dec_simple_name(d: ast.expr) -> str | None:
    if isinstance(d, ast.Name):
        return d.id
    if isinstance(d, ast.Attribute) and _is_name(d.value):
        return f"{getattr(d.value, 'id', None)}.{d.attr}"
    if isinstance(d, ast.Call) and _is_name(d.func):
        fn = d.func
        if isinstance(fn, ast.Name):
            return fn.id
    if sys.version_info >= (3, 9) and isinstance(d, ast.Call):
        if (
            isinstance(d.func, ast.Attribute)
            and isinstance(d.func.value, ast.Name)
            and d.func.value.id
        ):
            return d.func.attr
    return None


def _is_main_name_guard(
    t: ast.expr, py311: bool
) -> TypeGuard[ast.Compare]:
    if not isinstance(t, ast.Compare) or len(t.ops) != 1 or not isinstance(t.ops[0], ast.Eq):
        return False
    if not isinstance(t.left, ast.Name) or t.left.id != "__name__":
        return False
    if len(t.comparators) != 1:
        return False
    c0 = t.comparators[0]
    if isinstance(c0, ast.Constant) and isinstance(c0.value, str):
        return c0.value == "__main__"
    if (not py311) and isinstance(c0, ast.Str):
        return c0.s == "__main__"  # pragma: no cover
    return False


def _if_main_body_calls(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    py311 = sys.version_info >= (3, 8)
    for node in tree.body:
        if not isinstance(node, ast.If) or not _is_main_name_guard(
            node.test, py311
        ):
            continue
        for sub in ast.walk(node):
            if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name):
                out.add(sub.func.id)
    return out


def _add_parser_setdefaults(tree: ast.Module) -> set[str]:
    out: set[str] = set()
    for n in ast.walk(tree):
        if not isinstance(n, ast.Call) or not isinstance(
            n.func, ast.Attribute
        ):
            continue
        if n.func.attr != "set_defaults":
            continue
        for kw in n.keywords:
            if kw.arg in ("func", "handler", "action") and isinstance(
                kw.value, ast.Name
            ):
                out.add(kw.value.id)
    return out


ENTRY_DECORATOR_NAMES: frozenset[str] = frozenset(
    {
        "command",
        "route",
        "get",
        "post",
        "put",
        "delete",
        "patch",
        "task",
        "scheduled_task",
    }
)


def detect_entry_points(file_path: Path, root: Path) -> list[str]:
    """Return ``"relative/path.py:function"`` for likely entry points."""
    rel = _relpos(file_path, root)
    src = file_path.read_text(encoding="utf-8", errors="replace")
    try:
        tree = ast.parse(src, filename=str(file_path))
    except SyntaxError:
        return []

    out: set[str] = set()

    for fn in _if_main_body_calls(tree):
        out.add(f"{rel}:{fn}")

    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for d in node.decorator_list:
            dname = _dec_simple_name(d)
            if dname and dname.split(".")[-1] in ENTRY_DECORATOR_NAMES:
                out.add(f"{rel}:{node.name}")
                break
            if isinstance(d, ast.Name) and d.id in ENTRY_DECORATOR_NAMES:
                out.add(f"{rel}:{node.name}")
                break
            if isinstance(d, ast.Call) and d.func:
                tail = _dec_simple_name(d.func) or ""
                if tail.split(".")[-1] in ENTRY_DECORATOR_NAMES:
                    out.add(f"{rel}:{node.name}")
                break

    for fn in _add_parser_setdefaults(tree):
        out.add(f"{rel}:{fn}")

    return sorted(out)


def graph_id_for(relp: str, func: str) -> str:
    """``relp::func`` (forward slashes) — matches the verify / omnix graph."""
    r = relp.replace(os.sep, "/")
    return f"{r}::{func}"


