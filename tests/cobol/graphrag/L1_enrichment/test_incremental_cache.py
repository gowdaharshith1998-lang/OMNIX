from __future__ import annotations

from omnix.enrich.cache import EnrichmentCache
from tests.cobol.graphrag.helpers import graph


def test_stale_detection(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        cache = EnrichmentCache(store)
        assert cache.is_stale("prog:HELLO", "signatures", "a")
        cache.mark_enriched("prog:HELLO", "signatures", "a")
        assert not cache.is_stale("prog:HELLO", "signatures", "a")
        assert cache.is_stale("prog:HELLO", "signatures", "b")
    finally:
        store.close()


def test_cache_table_schema(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        EnrichmentCache(store)
        row = store.sqlite_connection().execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='enrichment_cache'"
        ).fetchone()
        assert row is not None
    finally:
        store.close()
