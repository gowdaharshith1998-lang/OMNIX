from __future__ import annotations

import asyncio

from omnix.enrich.logic import enrich_logic
from omnix.enrich.mock_provider import MockEnrichmentProvider
from tests.cobol.graphrag.helpers import graph, mark_enriched


def test_prompt_includes_neighbor_signatures(tmp_path) -> None:
    store = graph(tmp_path)
    provider = MockEnrichmentProvider()
    try:
        mark_enriched(store)
        asyncio.run(enrich_logic(store, ["prog:HELLO"], provider))
        assert "BYE signature" in provider.calls[0]["prompt"]
    finally:
        store.close()


def test_output_keys_populated(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        mark_enriched(store)
        asyncio.run(enrich_logic(store, ["prog:HELLO"], MockEnrichmentProvider()))
        node = next(n for n in store.iter_all_nodes() if n.id == "prog:HELLO")
        assert "logic_summary" in (node.metadata or {})
        assert "business_rules" in (node.metadata or {})
    finally:
        store.close()
