from __future__ import annotations

import asyncio

from omnix.enrich.communities import detect_communities, summarize_communities
from omnix.enrich.mock_provider import MockEnrichmentProvider
from tests.cobol.graphrag.helpers import graph, mark_enriched


def test_hierarchical_levels_produced(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        for idx in range(5):
            store.add_node(f"prog:P{idx}", f"P{idx}", "CobolProgram", metadata={"source_text": "x"})
            if idx:
                store.add_edge(f"prog:P{idx-1}", f"prog:P{idx}", "call")
        store.commit()
        hierarchy = detect_communities(store)
        assert 0 in hierarchy.levels
    finally:
        store.close()


def test_community_summary_persists(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        mark_enriched(store)
        for idx in range(5):
            store.add_node(f"prog:P{idx}", f"P{idx}", "CobolProgram", metadata={"signature_summary": "s"})
        store.commit()
        report = asyncio.run(summarize_communities(store, detect_communities(store), MockEnrichmentProvider()))
        assert report.processed >= 1
        assert any(n.type == "CobolCommunity" for n in store.iter_all_nodes())
    finally:
        store.close()


def test_graceful_skip_on_tiny_graph(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        hierarchy = detect_communities(store)
        assert hierarchy.skipped_reason
    finally:
        store.close()
