"""Bounded graph/code tools for LLM action dispatch.

Tool handlers read the live Studio ``GraphStore`` directly through a
``Workspace`` resolved by the dispatch route. They intentionally return small,
structured payloads so prompts cannot explode in size.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from omnix.graph.store import GraphStore, NodeRow

ToolName = Literal[
    "get_node_context",
    "find_callers",
    "find_callees",
    "find_related_files",
    "read_code_region",
]

_MAX_ROWS = 40
_MAX_TEXT_CHARS = 12_000
_MAX_REGION_LINES = 180


@dataclass(frozen=True)
class ToolContext:
    workspace_id: str
    project_id: str
    project_root: Path
    store: GraphStore


@dataclass(frozen=True)
class ToolStep:
    tool: str
    status: str
    result: dict[str, Any]
    truncated: bool = False
    error: str | None = None
    turn_number: int = 0
    args_summary: str = ""
    phase: str = "llm"
    tool_call_id: str | None = None


def run_tool(name: str, ctx: ToolContext, args: dict[str, Any]) -> ToolStep:
    """Execute a single graph/code tool by name (LLM tool-use entrypoint)."""
    return _execute_one(name, ctx, args)


def execute_tools(
    names: list[str],
    ctx: ToolContext,
    args: dict[str, Any] | None = None,
) -> list[ToolStep]:
    tool_args = args or {}
    out: list[ToolStep] = []
    for name in names:
        try:
            out.append(_execute_one(name, ctx, tool_args))
        except Exception as e:  # noqa: BLE001
            out.append(ToolStep(tool=name, status="error", result={}, error=str(e)))
    return out


def _execute_one(name: str, ctx: ToolContext, args: dict[str, Any]) -> ToolStep:
    if name == "get_node_context":
        return _get_node_context(ctx, _node_id(args))
    if name == "find_callers":
        return _find_refs(ctx, _node_id(args), as_target=True)
    if name == "find_callees":
        return _find_refs(ctx, _node_id(args), as_target=False)
    if name == "find_related_files":
        return _find_related_files(ctx, _file_path(args), _node_id(args, required=False))
    if name == "read_code_region":
        return _read_code_region(ctx, _file_path(args), args)
    return ToolStep(tool=name, status="error", result={}, error="unknown_tool")


def _node_id(args: dict[str, Any], *, required: bool = True) -> str:
    value = args.get("node_id") or args.get("selected_node_id")
    if isinstance(value, str) and value:
        return value
    if required:
        raise ValueError("node_id is required")
    return ""


def _file_path(args: dict[str, Any]) -> str:
    value = args.get("file_path") or args.get("path")
    if isinstance(value, str) and value:
        return value.replace("\\", "/")
    node_id = args.get("node_id") or args.get("selected_node_id")
    if isinstance(node_id, str) and "::" in node_id:
        return node_id.split("::", 1)[0]
    raise ValueError("file_path is required")


def _node_dict(n: NodeRow | None) -> dict[str, Any] | None:
    if n is None:
        return None
    return {
        "id": n.id,
        "name": n.name,
        "type": n.type,
        "file_path": n.file_path,
        "line_start": n.start_line,
        "line_end": n.end_line,
        "complexity": n.complexity,
        "metadata": n.metadata or {},
    }


def _get_node(store: GraphStore, node_id: str) -> NodeRow | None:
    for n in store.iter_all_nodes():
        if n.id == node_id:
            return n
    return None


def _get_node_context(ctx: ToolContext, node_id: str) -> ToolStep:
    node = _get_node(ctx.store, node_id)
    related_edges: list[dict[str, Any]] = []
    for edge in ctx.store.iter_all_edges():
        if edge.source_id == node_id or edge.target_id == node_id:
            related_edges.append(
                {
                    "id": edge.id,
                    "source_id": edge.source_id,
                    "target_id": edge.target_id,
                    "relationship": edge.relationship,
                    "metadata": edge.metadata or {},
                }
            )
        if len(related_edges) >= _MAX_ROWS:
            break
    return ToolStep(
        tool="get_node_context",
        status="ok",
        result={"node": _node_dict(node), "edges": related_edges},
        truncated=len(related_edges) >= _MAX_ROWS,
    )


def _find_refs(ctx: ToolContext, node_id: str, *, as_target: bool) -> ToolStep:
    ids: list[str] = []
    for edge in ctx.store.iter_all_edges():
        if edge.relationship != "CALLS":
            continue
        if as_target and edge.target_id == node_id:
            ids.append(edge.source_id)
        elif not as_target and edge.source_id == node_id:
            ids.append(edge.target_id)
        if len(ids) >= _MAX_ROWS:
            break
    found = [_node_dict(_get_node(ctx.store, nid)) for nid in ids]
    name = "find_callers" if as_target else "find_callees"
    return ToolStep(
        tool=name,
        status="ok",
        result={"node_id": node_id, "items": [x for x in found if x is not None]},
        truncated=len(ids) >= _MAX_ROWS,
    )


def _find_related_files(ctx: ToolContext, file_path: str, node_id: str = "") -> ToolStep:
    related: dict[str, dict[str, Any]] = {}
    node_ids = {
        n.id
        for n in ctx.store.iter_all_nodes()
        if n.file_path == file_path or (node_id and n.id == node_id)
    }
    for edge in ctx.store.iter_all_edges():
        if edge.source_id not in node_ids and edge.target_id not in node_ids:
            continue
        other_id = edge.target_id if edge.source_id in node_ids else edge.source_id
        other = _get_node(ctx.store, other_id)
        if not other or not other.file_path:
            continue
        bucket = related.setdefault(
            other.file_path,
            {"file_path": other.file_path, "relationships": set(), "nodes": []},
        )
        bucket["relationships"].add(edge.relationship)
        if len(bucket["nodes"]) < 8:
            bucket["nodes"].append(_node_dict(other))
        if len(related) >= _MAX_ROWS:
            break
    items = [
        {
            **value,
            "relationships": sorted(value["relationships"]),
        }
        for value in related.values()
    ]
    return ToolStep(
        tool="find_related_files",
        status="ok",
        result={"file_path": file_path, "items": items},
        truncated=len(related) >= _MAX_ROWS,
    )


def _read_code_region(
    ctx: ToolContext, file_path: str, args: dict[str, Any]
) -> ToolStep:
    rel = Path(file_path)
    if rel.is_absolute() or ".." in rel.parts:
        raise ValueError("file_path must be project-relative")
    full = (ctx.project_root / rel).resolve()
    root = ctx.project_root.resolve()
    if root not in full.parents and full != root:
        raise ValueError("file_path escapes workspace")
    start = int(args.get("line_start") or args.get("start_line") or 1)
    end_raw = args.get("line_end") or args.get("end_line")
    end = int(end_raw) if end_raw is not None else start + 80
    start = max(1, start)
    end = max(start, min(end, start + _MAX_REGION_LINES - 1))
    text = full.read_text(encoding="utf-8", errors="replace")
    lines = text.splitlines()
    snippet = "\n".join(lines[start - 1 : end])
    truncated = len(snippet) > _MAX_TEXT_CHARS or end < len(lines)
    if len(snippet) > _MAX_TEXT_CHARS:
        snippet = snippet[:_MAX_TEXT_CHARS]
    return ToolStep(
        tool="read_code_region",
        status="ok",
        result={
            "file_path": file_path,
            "line_start": start,
            "line_end": min(end, len(lines)),
            "text": snippet,
        },
        truncated=truncated,
    )
