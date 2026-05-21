from __future__ import annotations

from omnix.retrieval.vector_index import VectorIndex, cosine_similarity, embed_text
from tests.cobol.graphrag.helpers import graph, mark_enriched


def test_paraphrase_lookup_returns_target(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        mark_enriched(store)
        idx = VectorIndex(store)
        idx.rebuild_from_graph(store)
        assert idx.query("HELLO signature", "programs", top_k=5)
    finally:
        store.close()


def test_cosine_distance_sanity() -> None:
    v = embed_text("same text")
    assert cosine_similarity(v, v) > 0.99
