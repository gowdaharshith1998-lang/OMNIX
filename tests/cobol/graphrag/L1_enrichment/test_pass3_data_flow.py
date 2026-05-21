from __future__ import annotations

import asyncio

from omnix.enrich.data_flow import enrich_data_flow
from omnix.enrich.mock_provider import MockEnrichmentProvider
from tests.cobol.graphrag.helpers import graph, mark_enriched


def test_prompt_includes_related_context(tmp_path) -> None:
    store = graph(tmp_path)
    provider = MockEnrichmentProvider()
    try:
        mark_enriched(store)
        asyncio.run(enrich_data_flow(store, ["prog:HELLO"], provider))
        assert "related" in provider.calls[0]["prompt"]
    finally:
        store.close()


def test_data_flow_output_keys_populated(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        mark_enriched(store)
        asyncio.run(enrich_data_flow(store, ["prog:HELLO"], MockEnrichmentProvider()))
        node = next(n for n in store.iter_all_nodes() if n.id == "prog:HELLO")
        assert "data_flow_summary" in (node.metadata or {})
        assert "copybooks_resolved" in (node.metadata or {})
    finally:
        store.close()
