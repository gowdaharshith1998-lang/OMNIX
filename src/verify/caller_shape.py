"""SQLite graph: callers, literal types per parameter position, boundary sites."""

from __future__ import annotations

import ast
import os
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from . import boundary
from .boundary import _callee_name

_MAX_CALLSITES = 120
_MAX_SAME_FILE_EDGES = 10_000


def _open_ro(db: str) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{db}?mode=ro", uri=True)


def _rel_to_root(abs_f: str, root: str) -> str:
    t = Path(abs_f).resolve()
    r = Path(root).resolve()
    try:
        return str(t.relative_to(r)).replace("\\", "/")
    except (ValueError, OSError):
        return t.name


def _tid(relp: str, func: str) -> str:
    return f"{relp}::{func}"


def aggregate_caller_arg_types(
    graph_db: str, target_path: str, function_name: str, codebase_root: str
) -> dict[int, dict[str, int]]:
    """
    For each positional arg index, count literal ``type(value).__name__`` seen at
    call sites (graph CALLS to ``relp::function``). Caps number of call edges read.
    """
    if not graph_db or not Path(graph_db).is_file():
        print(
            f"omnix verify: no graph at {graph_db!r} — run `python3 omnix.py analyze <path>` first",
            file=sys.stderr,
        )
        return {}
    relp = _rel_to_root(str(Path(target_path).resolve()), str(Path(codebase_root).resolve()))
    tid = _tid(relp, function_name)
    con = _open_ro(str(Path(graph_db).resolve()))
    try:
        cur = con.execute(
            "SELECT e.source_id FROM edges e "
            "WHERE e.relationship = 'CALLS' AND e.target_id = ?"
            f" LIMIT {_MAX_SAME_FILE_EDGES}",
            (tid,),
        )
        sources = [r[0] for r in cur.fetchall()]
    finally:
        con.close()
    if len(sources) > _MAX_CALLSITES * 2:
        sources = sources[: _MAX_CALLSITES * 2]
    pos: dict[int, Counter[str]] = defaultdict(Counter)
    for sid in sources[:_MAX_CALLSITES]:
        if "::" not in str(sid):
            continue
        crel, cfn = str(sid).rsplit("::", 1)
        fpath = Path(codebase_root) / crel.replace("/", os.sep)
        if not fpath.is_file():
            continue
        try:
            tree = ast.parse(
                fpath.read_text(encoding="utf-8", errors="replace"),
                filename=str(fpath),
            )
        except (OSError, SyntaxError):
            continue
        for call in _calls_for_caller_in_module(tree, cfn, function_name):
            for i, arg in enumerate(call.args):
                if not isinstance(arg, ast.Constant):
                    continue
                v = arg.value
                lab = "None" if v is None else type(v).__name__
                if lab == "str":
                    lab = "str"
                pos[i][lab] += 1
    return {k: dict(v) for k, v in pos.items()}


def collect_literal_boundary_sites(
    graph_db: str, target_path: str, function_name: str, codebase_root: str
) -> list[tuple[dict[int, list[Any]], str]]:
    """(pos -> list of literal values) per call site, keyed by caller function id (e.g. rel::caller_a)."""
    if not graph_db or not Path(graph_db).is_file():
        return []
    relp = _rel_to_root(str(Path(target_path).resolve()), str(Path(codebase_root).resolve()))
    tid = _tid(relp, function_name)
    con = _open_ro(str(Path(graph_db).resolve()))
    try:
        sids = [
            r[0]
            for r in con.execute(
                "SELECT e.source_id FROM edges e "
                "WHERE e.relationship = 'CALLS' AND e.target_id = ? LIMIT ?",
                (tid, _MAX_SAME_FILE_EDGES),
            )
        ]
    finally:
        con.close()
    out: list[tuple[dict[int, list[Any]], str]] = []
    for sid in sids[:_MAX_CALLSITES]:
        if "::" not in str(sid):
            continue
        crel, cfn = str(sid).rsplit("::", 1)
        fpath = Path(codebase_root) / crel.replace("/", os.sep)
        if not fpath.is_file():
            continue
        try:
            tree = ast.parse(
                fpath.read_text(encoding="utf-8", errors="replace"),
                filename=str(fpath),
            )
        except (OSError, SyntaxError):
            continue
        for call in _calls_for_caller_in_module(tree, cfn, function_name):
            d = boundary.extract_literal_args_for_call(
                call, "", short_name=function_name
            )
            if d:
                out.append((d, str(sid)))
    return out


def _calls_for_caller_in_module(
    mod: ast.AST, caller_fn: str, callee_short: str
) -> list[ast.Call]:
    out: list[ast.Call] = []
    for fn, body in _all_functions_r(mod):
        if fn.name == caller_fn:
            for c in _calls_to_name_in_body(body, callee_short):
                out.append(c)
    return out


def _all_functions_r(
    mod: ast.AST,
) -> list[tuple[ast.FunctionDef | ast.AsyncFunctionDef, list[ast.stmt]]]:
    fns: list = []
    for n in ast.walk(mod):
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            fns.append((n, n.body))
    return fns  # type: ignore[return-value, arg-type]


def _calls_to_name_in_body(body: list[ast.stmt], name: str) -> list[ast.Call]:
    cands: list[ast.Call] = []
    for st in body:
        for c in ast.walk(st):
            if isinstance(c, ast.Call) and _callee_name(c) == name:
                cands.append(c)
    return cands
