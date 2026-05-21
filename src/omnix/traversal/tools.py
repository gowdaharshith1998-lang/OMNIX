"""The four bounded graph tools exposed to the traversal loop."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field

from omnix.enrich.common import enriched_text, get_node
from omnix.graph.store import GraphStore
from omnix.retrieval.graph_walker import walk_from


class QueryGraphArgs(BaseModel):
    cypher_like_query: str
    max_rows: int = Field(default=100, ge=1)


class ExpandNodeArgs(BaseModel):
    node_id: str
    edge_types: list[str]
    depth: int = Field(default=1, ge=1)


class SummarizeSubgraphArgs(BaseModel):
    node_ids: list[str]


class InspectDataItemArgs(BaseModel):
    item_name: str
    scope_program_id: str


ToolName = Literal["query_graph", "expand_node", "summarize_subgraph", "inspect_data_item"]


@dataclass(frozen=True)
class ToolSpec:
    name: ToolName
    description: str
    schema: type[BaseModel]


TOOL_SPECS: tuple[ToolSpec, ...] = (
    ToolSpec("query_graph", "Run a constrained cypher-like graph query.", QueryGraphArgs),
    ToolSpec("expand_node", "Expand a node along typed edges.", ExpandNodeArgs),
    ToolSpec("summarize_subgraph", "Summarize enriched node context.", SummarizeSubgraphArgs),
    ToolSpec("inspect_data_item", "Inspect a COBOL data item declaration and usages.", InspectDataItemArgs),
)


def tool_specs_for_prompt() -> list[dict[str, Any]]:
    return [
        {"name": spec.name, "description": spec.description, "schema": _schema(spec.schema)}
        for spec in TOOL_SPECS
    ]


def _schema(model: type[BaseModel]) -> dict[str, Any]:
    if hasattr(model, "model_json_schema"):
        return model.model_json_schema()  # type: ignore[attr-defined]
    return model.schema()


def dispatch_tool(graph_store: GraphStore, name: str, args: dict[str, Any]) -> Any:
    if name == "query_graph":
        query_args = QueryGraphArgs(**args)
        return query_graph(graph_store, query_args.cypher_like_query, query_args.max_rows)
    if name == "expand_node":
        expand_args = ExpandNodeArgs(**args)
        return expand_node(graph_store, expand_args.node_id, expand_args.edge_types, expand_args.depth)
    if name == "summarize_subgraph":
        summarize_args = SummarizeSubgraphArgs(**args)
        return summarize_subgraph(graph_store, summarize_args.node_ids)
    if name == "inspect_data_item":
        inspect_args = InspectDataItemArgs(**args)
        return inspect_data_item(graph_store, inspect_args.item_name, inspect_args.scope_program_id)
    raise ValueError(f"unknown traversal tool: {name}")


def parse_tool_call(model_output: str) -> tuple[str, dict[str, Any]] | None:
    text = model_output.strip()
    payload: Any
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
        if not match:
            return None
        try:
            payload = json.loads(match.group(1))
        except json.JSONDecodeError:
            return None
    if not isinstance(payload, dict):
        return None
    if "tool" in payload:
        name = str(payload["tool"])
        args = payload.get("args") or payload.get("arguments") or {}
    elif "tool_call" in payload and isinstance(payload["tool_call"], dict):
        call = payload["tool_call"]
        name = str(call.get("name") or call.get("tool"))
        args = call.get("args") or call.get("arguments") or {}
    else:
        return None
    return name, dict(args)


def query_graph(graph_store: GraphStore, cypher_like_query: str, max_rows: int = 100) -> list[dict[str, Any]]:
    """Small safe subset: optional name equality, optional relationship, return matching rows."""
    hard_cap = min(max(max_rows, 1), 1000)
    name_match = re.search(r"\bname\s*=\s*['\"]?([A-Za-z0-9_.:-]+)['\"]?", cypher_like_query)
    rel_match = re.search(r":([A-Za-z_]+)\]", cypher_like_query)
    target_name = name_match.group(1).upper() if name_match else None
    relationship = rel_match.group(1) if rel_match else None
    conn = graph_store.sqlite_connection()
    rows = conn.execute(
        """
        SELECT e.id AS edge_id, e.source_id, e.target_id, e.relationship,
               s.name AS source_name, t.name AS target_name, t.type AS target_type, t.metadata AS target_metadata
        FROM edges e
        JOIN nodes s ON s.id = e.source_id
        JOIN nodes t ON t.id = e.target_id
        ORDER BY e.id ASC
        LIMIT 1001
        """
    ).fetchall()
    out = []
    for row in rows:
        if relationship and str(row["relationship"]) != relationship:
            continue
        if target_name and target_name not in {str(row["source_name"]).upper(), str(row["target_name"]).upper()}:
            continue
        out.append(
            {
                "edge_id": row["edge_id"],
                "source_id": row["source_id"],
                "target_id": row["target_id"],
                "relationship": row["relationship"],
                "target_name": row["target_name"],
                "target_type": row["target_type"],
            }
        )
        if len(out) >= hard_cap:
            break
    if len(out) > 100:
        return [{"truncated": True, "rows": out[:100], "returned": 100, "matched": len(out)}]
    return out


def expand_node(
    graph_store: GraphStore,
    node_id: str,
    edge_types: list[str],
    depth: int = 1,
) -> list[dict[str, Any]]:
    rows = []
    for neighbor_id, hop in walk_from(graph_store, node_id, edge_types, max_depth=depth, max_nodes=200):
        node = get_node(graph_store, neighbor_id)
        if node is None:
            rows.append({"node_id": neighbor_id, "hop": hop, "missing": True})
            continue
        rows.append(
            {
                "node_id": node.id,
                "name": node.name,
                "type": node.type,
                "hop": hop,
                "summary": enriched_text(node),
            }
        )
    return rows


def summarize_subgraph(graph_store: GraphStore, node_ids: list[str]) -> str:
    parts = []
    for node_id in node_ids:
        node = get_node(graph_store, node_id)
        if node is None:
            continue
        parts.append(f"{node.name} ({node.type}): {enriched_text(node) or node.name}")
    return "\n".join(parts)


def inspect_data_item(graph_store: GraphStore, item_name: str, scope_program_id: str) -> dict[str, Any]:
    needle = item_name.upper()
    declarations = []
    usages = []
    for node in graph_store.iter_all_nodes():
        text = f"{node.name} {json.dumps(node.metadata or {}, sort_keys=True)}".upper()
        if needle not in text:
            continue
        row = {"node_id": node.id, "name": node.name, "type": node.type, "file_path": node.file_path}
        if node.type == "CobolDataItem":
            declarations.append(row)
        else:
            usages.append(row)
    return {
        "item_name": item_name,
        "scope_program_id": scope_program_id,
        "declarations": declarations,
        "usages": usages,
    }
