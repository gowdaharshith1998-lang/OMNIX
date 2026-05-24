"""Pass 3: program-level data-flow and JCL context summaries."""

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

PASS_NAME = "data_flow"
MODEL = "gpt-4.1"


async def enrich_data_flow(
    graph_store: GraphStore,
    node_ids: list[str] | None,
    fabric_provider: Any,
    *,
    batch_size: int = 50,
    max_cost_usd: float | None = None,
    force: bool = False,
    project_root: Path | None = None,
) -> EnrichmentReport:
    _ = batch_size
    cache = EnrichmentCache(graph_store)
    nodes = select_nodes(graph_store, node_ids, node_types={"CobolProgram", "CobolModule"})
    processed = 0
    skipped = 0
    spent = 0.0
    halted = False
    for node in nodes:
        source_sha = source_sha_for_node(node, project_root)
        if not force and not cache.is_stale(node.id, PASS_NAME, source_sha):
            skipped += 1
            continue
        if max_cost_usd is not None and spent >= max_cost_usd:
            halted = True
            break
        result = await call_fabric_provider(fabric_provider, _data_flow_prompt(graph_store, node), model=MODEL)
        content, cost = response_content(result)
        item = item_for_node(parse_jsonish(content), node) or {
            "data_flow_summary": f"{node.name} data flow inferred from COBOL graph.",
            "copybooks_resolved": [],
            "jcl_context": [],
        }
        update_node_metadata(
            graph_store,
            node.id,
            {
                "data_flow_summary": str(item.get("data_flow_summary") or ""),
                "copybooks_resolved": list(item.get("copybooks_resolved") or []),
                "jcl_context": item.get("jcl_context") or [],
            },
        )
        cache.mark_enriched(node.id, PASS_NAME, source_sha)
        spent += cost
        processed += 1
    return EnrichmentReport(PASS_NAME, processed, skipped, spent, halted)


def _data_flow_prompt(graph_store: GraphStore, node: NodeRow) -> str:
    related = []
    for neighbor in graph_store.get_neighbors(node.id):
        meta = dict(neighbor.metadata or {})
        related.append(
            {
                "id": neighbor.id,
                "type": neighbor.type,
                "name": neighbor.name,
                "signature": meta.get("signature_summary"),
                "logic": meta.get("logic_summary"),
            }
        )
    payload = {
        "node_id": node.id,
        "logic_summary": (node.metadata or {}).get("logic_summary") if node.metadata else None,
        "related": related,
    }
    return (
        "Return JSON with data_flow_summary, copybooks_resolved, and jcl_context.\n"
        + json.dumps(payload, sort_keys=True)
    )
