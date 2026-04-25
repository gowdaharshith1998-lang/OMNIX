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


# Decorators that do not break PBT when the underlying function is callables-like.
SAFE_DECORATORS: frozenset[str] = frozenset(
    {
        "staticmethod",
        "classmethod",
        "property",
        "cached_property",
        "lru_cache",
        "wraps",
        "total_ordering",
        "singledispatch",
        "abstractmethod",
        "override",
        "final",
    }
)

# Import roots whose decorators are treated as not plain callables.
FRAMEWORK_MODULES: frozenset[str] = frozenset(
    {
        "click",
        "typer",
        "fastapi",
        "flask",
        "starlette",
        "django",
        "celery",
        "pytest",
        "hypothesis",
        "asyncio",
    }
)

# Heuristic last-segment / bare-name names that often wrap framework or tests.
FRAMEWORK_ATTRS: frozenset[str] = frozenset(
    {
        "command",
        "group",
        "argument",
        "option",
        "get",
        "post",
        "put",
        "delete",
        "patch",
        "head",
        "options",
        "route",
        "websocket",
        "middleware",
        "on_event",
        "exception_handler",
        "before_request",
        "after_request",
        "task",
        "periodic_task",
        "shared_task",
        "fixture",
        "parametrize",
        "coroutine",
        "given",
        "settings",
    }
)


def _unwrap_decorator_func(dec_node: ast.expr) -> ast.expr:
    d = dec_node
    while isinstance(d, ast.Call):
        d = d.func
    return d


def _django_like_decorator_id(dec_node: ast.expr) -> str:
    d = _unwrap_decorator_func(dec_node)
    if isinstance(d, ast.Name):
        return d.id
    if isinstance(d, ast.Attribute):
        return d.attr
    return ""


def _is_django_skip_pattern(dec_node: ast.expr) -> bool:
    n = _django_like_decorator_id(dec_node)
    if not n:
        return False
    if "login_required" in n or "csrf_exempt" in n:
        return True
    if n.startswith("require_"):
        return True
    return False


def _decorator_signature(dec_node: ast.expr) -> tuple:
    d = _unwrap_decorator_func(dec_node)
    if isinstance(d, ast.Name):
        return ("name", d.id)
    if isinstance(d, ast.Attribute):
        if isinstance(d.value, ast.Name):
            return ("attr", d.value.id, d.attr)
        return ("attr", "?", d.attr)
    return ("unknown",)


def _format_decorator_id(dec_node: ast.expr) -> str:
    d = _unwrap_decorator_func(dec_node)
    if isinstance(d, ast.Name):
        return d.id
    if isinstance(d, ast.Attribute) and isinstance(d.value, ast.Name):
        return f"{d.value.id}.{d.attr}"
    if isinstance(d, ast.Attribute):
        return d.attr
    return "unknown"


def _is_safe_decorator(dec_node: ast.expr) -> bool:
    d = _unwrap_decorator_func(dec_node)
    if isinstance(d, ast.Name) and d.id in SAFE_DECORATORS:
        return True
    if isinstance(d, ast.Attribute) and d.attr in SAFE_DECORATORS:
        return True
    return False


def _is_unsafe_decorator(dec_node: ast.expr) -> bool:
    if _is_django_skip_pattern(dec_node):
        return True
    sig = _decorator_signature(dec_node)
    if sig[0] == "name" and len(sig) >= 2:
        n = str(sig[1])
        if n in SAFE_DECORATORS:
            return False
        if n in FRAMEWORK_ATTRS:
            return True
        return False
    if sig[0] == "attr" and len(sig) >= 3:
        mod, att = str(sig[1]), str(sig[2])
        if att in SAFE_DECORATORS:
            return False
        if mod == "asyncio" and att == "coroutine":
            return True
        if mod in FRAMEWORK_MODULES and mod != "asyncio":
            return True
        if att in FRAMEWORK_ATTRS:
            return True
        return False
    if sig[0] == "unknown":
        return False
    return False


def detect_framework_decorated(file_path: Path) -> list[tuple[str, str]]:
    """Top-level only (matches :func:`verify.signature.extract_signatures`).

    Return ``(function_name, reason)`` for functions to skip before PBT.
    """
    try:
        src = file_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    try:
        tree = ast.parse(src, filename=str(file_path))
    except SyntaxError:
        return []
    return _detect_framework_from_tree(tree)


def _detect_framework_from_tree(tree: ast.Module) -> list[tuple[str, str]]:
    skipped: list[tuple[str, str]] = []
    for node in tree.body:
        if isinstance(node, ast.AsyncFunctionDef):
            skipped.append((node.name, "async_top_level"))
            continue
        if not isinstance(node, ast.FunctionDef):
            continue
        if not node.decorator_list:
            continue
        uids: list[str] = []
        for d in node.decorator_list:
            if _is_django_skip_pattern(d) or _is_unsafe_decorator(d):
                uids.append(_format_decorator_id(d))
        if uids:
            skipped.append(
                (node.name, f"framework_decorator:{','.join(uids)}")
            )
            continue
        if len(node.decorator_list) >= 2 and not all(
            _is_safe_decorator(d) for d in node.decorator_list
        ):
            skipped.append((node.name, "multiple_decorators"))
    return skipped


def graph_id_for(relp: str, func: str) -> str:
    """``relp::func`` (forward slashes) — matches the verify / omnix graph."""
    r = relp.replace(os.sep, "/")
    return f"{r}::{func}"


