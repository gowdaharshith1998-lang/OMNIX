from __future__ import annotations

from omnix.retrieval.hybrid import retrieve
from tests.cobol.graphrag.helpers import graph


def test_no_enrichment_two_channel_fallback(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        bundle = retrieve(store, "prog:HELLO", budget_tokens=1000)
        assert bundle.included
        assert bundle.retrieval_modes["vector"] == 0
    finally:
        store.close()
