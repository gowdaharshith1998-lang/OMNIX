from __future__ import annotations

import pytest


class FakeCrossEncoder:
    def __init__(self, scores: list[float]) -> None:
        self.scores = scores
        self.calls: list[list[list[str]]] = []

    def predict(self, pairs: list[list[str]]) -> list[float]:
        self.calls.append(pairs)
        return self.scores[: len(pairs)]


def test_off_mode_passes_through_without_model_load(monkeypatch) -> None:
    from omnix.retrieval import reranker

    monkeypatch.setenv("OMNIX_GRAPHRAG_RERANK_MODE", "off")
    monkeypatch.setattr(reranker, "_load_reranker", lambda: pytest.fail("model should not load"))

    assert reranker.rerank("q", ["a", "b", "c"], top_n=2) == [(0, 0.0), (1, 0.0)]


def test_auto_mode_falls_back_when_unavailable(monkeypatch) -> None:
    from omnix.retrieval import reranker

    monkeypatch.setenv("OMNIX_GRAPHRAG_RERANK_MODE", "auto")
    monkeypatch.setattr(reranker, "_load_reranker", lambda: None)

    assert reranker.rerank("q", ["a", "b"], top_n=10) == [(0, 0.0), (1, 0.0)]


def test_on_mode_raises_when_unavailable(monkeypatch) -> None:
    from omnix.retrieval import reranker

    monkeypatch.setenv("OMNIX_GRAPHRAG_RERANK_MODE", "on")
    monkeypatch.setattr(reranker, "_load_reranker", lambda: None)

    with pytest.raises(RuntimeError, match="reranker unavailable"):
        reranker.rerank("q", ["a"], top_n=1)


def test_scores_and_orders_with_fake_model(monkeypatch) -> None:
    from omnix.retrieval import reranker

    fake = FakeCrossEncoder([0.9, 0.1, 0.5])
    reranker._SCORE_CACHE.clear()
    monkeypatch.setenv("OMNIX_GRAPHRAG_RERANK_MODE", "auto")
    monkeypatch.setattr(reranker, "_load_reranker", lambda: fake)

    assert reranker.rerank("q", ["best", "worst", "mid"], top_n=3) == [(0, 0.9), (2, 0.5), (1, 0.1)]


def test_cache_hits_skip_model_call(monkeypatch) -> None:
    from omnix.retrieval import reranker

    fake = FakeCrossEncoder([0.7])
    reranker._SCORE_CACHE.clear()
    monkeypatch.setenv("OMNIX_GRAPHRAG_RERANK_MODE", "auto")
    monkeypatch.setattr(reranker, "_load_reranker", lambda: fake)

    assert reranker.rerank("q", ["doc"], top_n=1) == [(0, 0.7)]
    assert reranker.rerank("q", ["doc"], top_n=1) == [(0, 0.7)]
    assert len(fake.calls) == 1


def test_top_n_truncation(monkeypatch) -> None:
    from omnix.retrieval import reranker

    fake = FakeCrossEncoder([0.1, 0.4, 0.3])
    reranker._SCORE_CACHE.clear()
    monkeypatch.setenv("OMNIX_GRAPHRAG_RERANK_MODE", "auto")
    monkeypatch.setattr(reranker, "_load_reranker", lambda: fake)

    assert reranker.rerank("q", ["a", "b", "c"], top_n=2) == [(1, 0.4), (2, 0.3)]
