from __future__ import annotations

from omnix.retrieval.bm25_index import Bm25Index
from tests.cobol.graphrag.helpers import graph, mark_enriched


def test_known_token_lookup(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        mark_enriched(store)
        idx = Bm25Index(store)
        idx.rebuild_from_graph(store)
        assert idx.query("HELLO")[0][0] == "prog:HELLO"
    finally:
        store.close()
