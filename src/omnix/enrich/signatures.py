"""Pass 1: compact signatures for COBOL programs and paragraphs."""

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
    source_for_node,
    source_sha_for_node,
    truncate_source,
    update_node_metadata,
    utc_now_iso,
)
from omnix.graph.store import GraphStore, NodeRow

PASS_NAME = "signatures"
MODEL = "claude-haiku-4.5"


async def enrich_signatures(
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
    candidates = select_nodes(
        graph_store, node_ids, node_types={"CobolProgram", "CobolParagraph", "CobolModule"}
    )
    pending: list[tuple[NodeRow, str]] = []
    skipped = 0
    for node in candidates:
        source_sha = source_sha_for_node(node, project_root)
        if not force and not cache.is_stale(node.id, PASS_NAME, source_sha):
            skipped += 1
            continue
        pending.append((node, source_sha))

    processed = 0
    spent = 0.0
    halted = False
    for start in range(0, len(pending), max(1, batch_size)):
        batch = pending[start : start + max(1, batch_size)]
        if max_cost_usd is not None and spent >= max_cost_usd:
            halted = True
            break
        prompt = _signature_prompt([node for node, _sha in batch], project_root)
        result = await call_fabric_provider(fabric_provider, prompt, model=MODEL)
        content, cost = response_content(result)
        parsed = parse_jsonish(content)
        per_node_cost = cost / max(1, len(batch))
        for node, source_sha in batch:
            if max_cost_usd is not None and spent + per_node_cost > max_cost_usd:
                halted = True
                break
            item = item_for_node(parsed, node) or _heuristic_signature(node, project_root)
            updates = {
                "signature_summary": str(item.get("signature_summary") or "")[:240],
                "signature_inputs": list(item.get("signature_inputs") or []),
                "signature_outputs": list(item.get("signature_outputs") or []),
                "signature_enriched_at": utc_now_iso(),
            }
            update_node_metadata(graph_store, node.id, updates)
            cache.mark_enriched(node.id, PASS_NAME, source_sha)
            processed += 1
            spent += per_node_cost
        if halted:
            break
    return EnrichmentReport(
        PASS_NAME,
        processed=processed,
        skipped=skipped,
        cost_usd=spent,
        halted=halted,
        details={"candidate_count": len(candidates)},
    )


def _signature_prompt(nodes: list[NodeRow], project_root: Path | None) -> str:
    payload = []
    for node in nodes:
        meta = dict(node.metadata or {})
        payload.append(
            {
                "node_id": node.id,
                "name": node.name,
                "type": node.type,
                "division": meta.get("division"),
                "section": meta.get("section"),
                "source": truncate_source(source_for_node(node, project_root)),
            }
        )
    return (
        "You enrich COBOL graph nodes. Return strict JSON keyed by node_id with "
        "signature_summary, signature_inputs, signature_outputs.\n"
        + json.dumps(payload, sort_keys=True)
    )


def _heuristic_signature(node: NodeRow, project_root: Path | None) -> dict[str, Any]:
    text = source_for_node(node, project_root)
    words = " ".join(line.strip() for line in text.splitlines()[:6])
    return {
        "signature_summary": f"{node.type} {node.name}: {words[:180]}",
        "signature_inputs": [],
        "signature_outputs": [],
    }
