"""Shared helpers for COBOL GraphRAG enrichment."""

from __future__ import annotations

import inspect
import json
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from omnix.graph.store import GraphStore, NodeRow


@dataclass(frozen=True)
class EnrichmentReport:
    pass_name: str
    processed: int = 0
    skipped: int = 0
    cost_usd: float = 0.0
    halted: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OverallReport:
    reports: tuple[EnrichmentReport, ...]
    total_cost_usd: float


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return sha256(text.encode("utf-8", errors="replace")).hexdigest()


def graph_db_path(codebase_root: Path) -> Path:
    omnix_dir = codebase_root / ".omnix"
    graph_db = omnix_dir / "graph.db"
    legacy_db = omnix_dir / "omnix.db"
    if graph_db.exists():
        return graph_db
    if legacy_db.exists():
        return legacy_db
    omnix_dir.mkdir(parents=True, exist_ok=True)
    return graph_db


def get_node(graph_store: GraphStore, node_id: str) -> NodeRow | None:
    row = graph_store.sqlite_connection().execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
    if row is None:
        return None
    return NodeRow(
        id=str(row["id"]),
        name=str(row["name"]),
        type=str(row["type"]),
        file_path=row["file_path"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        complexity=int(row["complexity"] or 0),
        metadata=json.loads(row["metadata"]) if row["metadata"] else None,
    )


def update_node_metadata(graph_store: GraphStore, node_id: str, updates: dict[str, Any]) -> None:
    node = get_node(graph_store, node_id)
    if node is None:
        raise KeyError(f"node not found: {node_id}")
    metadata = dict(node.metadata or {})
    metadata.update(updates)
    graph_store.sqlite_connection().execute(
        "UPDATE nodes SET metadata = ? WHERE id = ?",
        (json.dumps(metadata, sort_keys=True), node_id),
    )
    graph_store.commit()


def select_nodes(
    graph_store: GraphStore,
    node_ids: Iterable[str] | None,
    *,
    node_types: set[str] | None = None,
) -> list[NodeRow]:
    if node_ids is not None:
        out = [node for node_id in node_ids if (node := get_node(graph_store, str(node_id))) is not None]
    else:
        out = list(graph_store.iter_all_nodes())
    if node_types is not None:
        out = [node for node in out if node.type in node_types]
    return out


def source_for_node(node: NodeRow, project_root: Path | None = None) -> str:
    meta = dict(node.metadata or {})
    for key in ("source_text", "raw_source", "text"):
        val = meta.get(key)
        if isinstance(val, str) and val:
            return val
    if node.file_path:
        p = Path(node.file_path)
        if not p.is_absolute() and project_root is not None:
            p = project_root / p
        if p.is_file():
            text = p.read_text(encoding="utf-8", errors="replace")
            if node.start_line and node.end_line and node.end_line >= node.start_line:
                lines = text.splitlines()
                return "\n".join(lines[node.start_line - 1 : node.end_line])
            return text
    return node.name


def source_sha_for_node(node: NodeRow, project_root: Path | None = None) -> str:
    return sha256_text(source_for_node(node, project_root))


def truncate_source(text: str, limit: int = 3000) -> str:
    return text if len(text) <= limit else text[:limit] + "\n...[truncated]"


async def call_fabric_provider(
    fabric_provider: Any,
    prompt: str,
    *,
    model: str,
    json_mode: bool = True,
    system_prompt: str | None = None,
) -> Any:
    if fabric_provider is None:
        raise RuntimeError("fabric_provider is required for live enrichment")
    kwargs = {"prompt": prompt, "model": model, "json_mode": json_mode}
    if system_prompt is not None:
        kwargs["system_prompt"] = system_prompt
    if hasattr(fabric_provider, "complete"):
        result = fabric_provider.complete(**kwargs)
    elif hasattr(fabric_provider, "dispatch"):
        result = fabric_provider.dispatch(**kwargs)
    elif callable(fabric_provider):
        try:
            result = fabric_provider(**kwargs)
        except TypeError:
            result = fabric_provider(prompt)
    else:
        raise TypeError("fabric_provider must be callable or expose complete/dispatch")
    if inspect.isawaitable(result):
        result = await result
    return result


def response_content(result: Any) -> tuple[Any, float]:
    cost = 0.0
    content = result
    if isinstance(result, dict):
        raw_cost = result.get("cost_usd")
        if isinstance(raw_cost, int | float):
            cost = float(raw_cost)
        for key in ("content", "response", "text", "json"):
            if key in result:
                content = result[key]
                break
    elif hasattr(result, "content"):
        content = result.content
        raw_cost = getattr(result, "cost_usd", 0.0)
        if isinstance(raw_cost, int | float):
            cost = float(raw_cost)
    return content, cost


def parse_jsonish(value: Any) -> Any:
    if isinstance(value, dict | list):
        return value
    if not isinstance(value, str):
        return {}
    text = value.strip()
    if not text:
        return {}
    fenced = re.search(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL)
    if fenced:
        text = fenced.group(1).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return {}
    return {}


def item_for_node(parsed: Any, node: NodeRow) -> dict[str, Any]:
    if isinstance(parsed, list):
        for item in parsed:
            if isinstance(item, dict) and item.get("node_id") in {node.id, node.name}:
                return item
        return parsed[0] if parsed and isinstance(parsed[0], dict) else {}
    if not isinstance(parsed, dict):
        return {}
    if node.id in parsed and isinstance(parsed[node.id], dict):
        return dict(parsed[node.id])
    if node.name in parsed and isinstance(parsed[node.name], dict):
        return dict(parsed[node.name])
    if "nodes" in parsed and isinstance(parsed["nodes"], list):
        return item_for_node(parsed["nodes"], node)
    return dict(parsed)


def enriched_text(node: NodeRow) -> str:
    meta = dict(node.metadata or {})
    parts = [
        node.name,
        str(meta.get("signature_summary") or ""),
        str(meta.get("logic_summary") or ""),
        str(meta.get("data_flow_summary") or ""),
        " ".join(str(x) for x in meta.get("business_rules") or []),
    ]
    return "\n".join(part for part in parts if part.strip())


def has_enrichment(node: NodeRow | None) -> bool:
    if node is None:
        return False
    meta = dict(node.metadata or {})
    return any(meta.get(key) for key in ("signature_summary", "logic_summary", "data_flow_summary"))
