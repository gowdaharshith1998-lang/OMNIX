from __future__ import annotations

import asyncio

from omnix.enrich.mock_provider import MockEnrichmentProvider
from omnix.enrich.signatures import enrich_signatures
from tests.cobol.graphrag.helpers import graph


def test_signature_keys_populated(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        report = asyncio.run(enrich_signatures(store, ["prog:HELLO"], MockEnrichmentProvider()))
        node = next(n for n in store.iter_all_nodes() if n.id == "prog:HELLO")
        assert report.processed == 1
        assert "signature_summary" in (node.metadata or {})
        assert "signature_inputs" in (node.metadata or {})
    finally:
        store.close()


def test_batch_dispatched(tmp_path) -> None:
    store = graph(tmp_path)
    provider = MockEnrichmentProvider()
    try:
        asyncio.run(
            enrich_signatures(
                store,
                ["prog:HELLO", "para:HELLO:MAIN"],
                provider,
                batch_size=1,
            )
        )
        assert len(provider.calls) == 2
    finally:
        store.close()


def test_cache_skip_on_no_change(tmp_path) -> None:
    store = graph(tmp_path)
    provider = MockEnrichmentProvider()
    try:
        asyncio.run(enrich_signatures(store, ["prog:HELLO"], provider))
        report = asyncio.run(enrich_signatures(store, ["prog:HELLO"], provider))
        assert report.skipped == 1
    finally:
        store.close()


def test_budget_halt_clean(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        report = asyncio.run(
            enrich_signatures(
                store,
                ["prog:HELLO", "para:HELLO:MAIN"],
                MockEnrichmentProvider(),
                batch_size=2,
                max_cost_usd=0.0001,
            )
        )
        assert report.halted
        assert report.processed == 0
    finally:
        store.close()
