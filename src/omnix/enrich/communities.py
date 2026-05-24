"""Pass 4: dependency community detection and summaries."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

from omnix.enrich.common import (
    EnrichmentReport,
    call_fabric_provider,
    response_content,
    update_node_metadata,
)
from omnix.graph.store import GraphStore, NodeRow

PASS_NAME = "communities"
MODEL = "gpt-4.1"
DEPENDENCY_EDGES = {
    "CALLS",
    "COPIES",
    "INVOKES",
    "call",
    "perform",
    "invokes",
    "reads_file",
    "writes_file",
}


@dataclass(frozen=True)
class CommunityHierarchy:
    levels: dict[int, dict[str, set[str]]]
    skipped_reason: str | None = None


def detect_communities(graph_store: GraphStore) -> CommunityHierarchy:
    programs = [n for n in graph_store.iter_all_nodes() if n.type in {"CobolProgram", "CobolModule"}]
    if len(programs) < 5:
        return CommunityHierarchy({}, f"Insufficient nodes for community detection (n={len(programs)})")
    program_ids = {n.id for n in programs}
    adjacency: dict[str, set[str]] = {n.id: set() for n in programs}
    for edge in graph_store.iter_all_edges():
        if edge.relationship not in DEPENDENCY_EDGES:
            continue
        if edge.source_id in program_ids and edge.target_id in program_ids:
            adjacency[edge.source_id].add(edge.target_id)
            adjacency[edge.target_id].add(edge.source_id)

    visited: set[str] = set()
    communities: dict[str, set[str]] = {}
    for node_id in sorted(program_ids):
        if node_id in visited:
            continue
        stack = [node_id]
        group: set[str] = set()
        while stack:
            cur = stack.pop()
            if cur in group:
                continue
            group.add(cur)
            stack.extend(sorted(adjacency.get(cur, set()) - group))
        visited |= group
        communities[f"c{len(communities)}"] = group
    return CommunityHierarchy({0: communities})


async def summarize_communities(
    graph_store: GraphStore,
    hierarchy: CommunityHierarchy,
    fabric_provider: Any,
) -> EnrichmentReport:
    if hierarchy.skipped_reason:
        return EnrichmentReport(PASS_NAME, skipped=1, details={"reason": hierarchy.skipped_reason})
    processed = 0
    spent = 0.0
    for level, communities in hierarchy.levels.items():
        for community_id, members in communities.items():
            community_node_id = f"cobol-community::{level}::{community_id}"
            payload = [_node_summary(graph_store, node_id) for node_id in sorted(members)]
            result = await call_fabric_provider(
                fabric_provider,
                "Summarize this COBOL subsystem as JSON with community_summary:\n"
                + json.dumps(payload, sort_keys=True),
                model=MODEL,
            )
            content, cost = response_content(result)
            summary = "COBOL subsystem containing " + ", ".join(item["name"] for item in payload)
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                    summary = str(parsed.get("community_summary") or summary)
                except json.JSONDecodeError:
                    summary = content.strip() or summary
            elif isinstance(content, dict):
                summary = str(content.get("community_summary") or summary)
            graph_store.add_node(
                community_node_id,
                f"Community {community_id}",
                "CobolCommunity",
                metadata={"level": level, "community_id": community_id, "community_summary": summary},
            )
            for member in members:
                graph_store.add_edge(member, community_node_id, "MEMBER_OF", {"level": level})
            update_node_metadata(graph_store, community_node_id, {"community_summary": summary})
            spent += cost
            processed += 1
    graph_store.commit()
    return EnrichmentReport(PASS_NAME, processed=processed, cost_usd=spent)


def _node_summary(graph_store: GraphStore, node_id: str) -> dict[str, Any]:
    row = graph_store.sqlite_connection().execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
    if row is None:
        return {"id": node_id, "name": node_id, "signature": ""}
    node = NodeRow(
        id=str(row["id"]),
        name=str(row["name"]),
        type=str(row["type"]),
        file_path=row["file_path"],
        start_line=row["start_line"],
        end_line=row["end_line"],
        complexity=int(row["complexity"] or 0),
        metadata=json.loads(row["metadata"]) if row["metadata"] else None,
    )
    return {
        "id": node.id,
        "name": node.name,
        "signature": (node.metadata or {}).get("signature_summary", ""),
    }
