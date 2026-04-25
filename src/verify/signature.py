"""AST-based Python function signature extraction."""

from __future__ import annotations

import ast
import logging
from pathlib import Path
from typing import Any

_log = logging.getLogger("verify.signature")


def extract_signatures(
    file_path: Path | str, function_name: str | None = None, *, source: str | None = None
) -> list[dict[str, Any]]:
    p = Path(file_path)
    src = source if source is not None else p.read_text(encoding="utf-8")
    tree = ast.parse(src, filename=str(p))
    out: list[dict[str, Any]] = []
    for node in tree.body:
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        if function_name and node.name != function_name:
            continue
        if node.args.vararg is not None:
            _log.warning("skipping *%s in %s", node.args.vararg.arg, node.name)
        if node.args.kwarg is not None:
            _log.warning("skipping **%s in %s", node.args.kwarg.arg, node.name)

        posonly: list[ast.arg] = list(node.args.posonlyargs)
        normal: list[ast.arg] = list(node.args.args)
        all_pos: list[ast.arg] = posonly + normal
        sk: set[ast.arg] = {a for a in (node.args.vararg, node.args.kwarg) if a is not None}

        params: list[tuple[str, str | None]] = []
        for a in all_pos:
            if a in sk:
                continue
            if a.annotation is not None:
                params.append((a.arg, ast.unparse(a.annotation)))
            else:
                params.append((a.arg, None))

        defaults: dict[str, str] = {}
        defaults_list = list(node.args.defaults)
        n_defaults = len(defaults_list)
        n_params = len(all_pos)
        for j, dnode in enumerate(defaults_list):
            a = all_pos[n_params - n_defaults + j]
            if a in sk:
                continue
            defaults[a.arg] = ast.unparse(dnode) if dnode is not None else "None"
        ret: str | None = (
            ast.unparse(node.returns) if node.returns is not None else None
        )
        out.append(
            {
                "name": node.name,
                "params": params,
                "return_hint": ret,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "lineno": node.lineno,
                "defaults": defaults,
            }
        )
    return out
