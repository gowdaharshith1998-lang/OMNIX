from __future__ import annotations

from omnix.retrieval import hybrid
from tests.cobol.graphrag.helpers import graph, mark_enriched


def test_retrieve_invokes_reranker_when_enabled(tmp_path, monkeypatch) -> None:
    store = graph(tmp_path)
    try:
        mark_enriched(store)
        calls = []

        def fake_rerank(query: str, docs: list[str], top_n: int = 10) -> list[tuple[int, float]]:
            calls.append((query, docs, top_n))
            return [(idx, float(len(docs) - idx)) for idx in range(min(top_n, len(docs)))]

        monkeypatch.setenv("OMNIX_GRAPHRAG_RERANK_MODE", "auto")
        monkeypatch.setattr(hybrid, "rerank", fake_rerank)

        bundle = hybrid.retrieve(store, "prog:HELLO", budget_tokens=1000)

        assert calls
        assert bundle.retrieval_modes["rerank"] == len(calls[0][1])
    finally:
        store.close()
