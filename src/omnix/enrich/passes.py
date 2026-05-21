"""Orchestrate COBOL GraphRAG enrichment passes."""

from __future__ import annotations

from typing import Any

from omnix.enrich.common import OverallReport
from omnix.enrich.communities import detect_communities, summarize_communities
from omnix.enrich.data_flow import enrich_data_flow
from omnix.enrich.logic import enrich_logic
from omnix.enrich.signatures import enrich_signatures
from omnix.graph.store import GraphStore


def parse_passes(passes: str | list[int] | tuple[int, ...]) -> list[int]:
    if isinstance(passes, str):
        text = passes.strip().lower()
        if text in {"all", "1,2,3,4"}:
            return [1, 2, 3, 4]
        return [int(part.strip()) for part in text.split(",") if part.strip()]
    return [int(p) for p in passes]


async def run_passes(
    graph_store: GraphStore,
    fabric_provider: Any,
    passes: list[int] | str,
    budget_usd: float | None = None,
    batch_size: int = 50,
    force: bool = False,
) -> OverallReport:
    reports = []
    remaining = budget_usd
    for pass_id in parse_passes(passes):
        if pass_id == 1:
            report = await enrich_signatures(
                graph_store,
                None,
                fabric_provider,
                batch_size=batch_size,
                max_cost_usd=remaining,
                force=force,
            )
        elif pass_id == 2:
            report = await enrich_logic(
                graph_store,
                None,
                fabric_provider,
                batch_size=batch_size,
                max_cost_usd=remaining,
                force=force,
            )
        elif pass_id == 3:
            report = await enrich_data_flow(
                graph_store,
                None,
                fabric_provider,
                batch_size=batch_size,
                max_cost_usd=remaining,
                force=force,
            )
        elif pass_id == 4:
            report = await summarize_communities(graph_store, detect_communities(graph_store), fabric_provider)
        elif pass_id == 5:
            from omnix.retrieval.bm25_index import Bm25Index
            from omnix.retrieval.vector_index import VectorIndex

            Bm25Index(graph_store).rebuild_from_graph(graph_store)
            VectorIndex(graph_store).rebuild_from_graph(graph_store)
            continue
        else:
            raise ValueError(f"unknown enrichment pass: {pass_id}")
        reports.append(report)
        if remaining is not None:
            remaining = max(0.0, remaining - report.cost_usd)
        if report.halted:
            break
    if 4 in parse_passes(passes):
        from omnix.retrieval.bm25_index import Bm25Index
        from omnix.retrieval.vector_index import VectorIndex

        Bm25Index(graph_store).rebuild_from_graph(graph_store)
        VectorIndex(graph_store).rebuild_from_graph(graph_store)
    return OverallReport(tuple(reports), sum(report.cost_usd for report in reports))
