"""Pass 2: logic summaries and business rules."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from omnix.enrich.cache import EnrichmentCache
from omnix.enrich.common import (
    EnrichmentReport,
    call_fabric_provider,
    item_for_node,
    parse_jsonish,
    response_content,
    select_nodes,
    source_sha_for_node,
    update_node_metadata,
)
from omnix.graph.store import GraphStore, NodeRow

PASS_NAME = "logic"
MODEL = "claude-sonnet-4.6"


async def enrich_logic(
    graph_store: GraphStore,
    node_ids: list[str] | None,
    fabric_provider: Any,
    *,
    batch_size: int = 50,
    max_cost_usd: float | None = None,
    force: bool = False,
    project_root: Path | None = None,
) -> EnrichmentReport:
    cache = EnrichmentCache(graph_store)
    nodes = select_nodes(
        graph_store, node_ids, node_types={"CobolProgram", "CobolParagraph", "CobolModule"}
    )
    pending: list[tuple[NodeRow, str]] = []
    skipped = 0
    for node in nodes:
        source_sha = source_sha_for_node(node, project_root)
        if not force and not cache.is_stale(node.id, PASS_NAME, source_sha):
            skipped += 1
            continue
        pending.append((node, source_sha))

    processed = 0
    spent = 0.0
    halted = False
    for node, source_sha in pending:
        if max_cost_usd is not None and spent >= max_cost_usd:
            halted = True
            break
        prompt = _logic_prompt(graph_store, node)
        result = await call_fabric_provider(
            fabric_provider,
            prompt,
            model=MODEL,
            system_prompt="COBOL logic enrichment JSON-only pass.",
        )
        content, cost = response_content(result)
        item = item_for_node(parse_jsonish(content), node) or {
            "logic_summary": f"{node.name} executes its COBOL procedure flow.",
            "business_rules": [],
        }
        update_node_metadata(
            graph_store,
            node.id,
            {
                "logic_summary": str(item.get("logic_summary") or ""),
                "business_rules": list(item.get("business_rules") or []),
            },
        )
        cache.mark_enriched(node.id, PASS_NAME, source_sha)
        spent += cost
        processed += 1
    return EnrichmentReport(PASS_NAME, processed, skipped, spent, halted, {"batch_size": batch_size})


def _logic_prompt(graph_store: GraphStore, node: NodeRow) -> str:
    neighbors = []
    for neighbor in graph_store.get_neighbors(node.id):
        meta = dict(neighbor.metadata or {})
        if meta.get("signature_summary"):
            neighbors.append({"id": neighbor.id, "name": neighbor.name, "signature": meta["signature_summary"]})
    payload = {
        "node_id": node.id,
        "name": node.name,
        "signature": (node.metadata or {}).get("signature_summary") if node.metadata else None,
        "neighbors": neighbors,
    }
    return (
        "Return JSON with logic_summary and business_rules for this COBOL node.\n"
        + json.dumps(payload, sort_keys=True)
    )
