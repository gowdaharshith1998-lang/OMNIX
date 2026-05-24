"""Cross-encoder reranker with hash-cache and opt-in env gating."""

from __future__ import annotations

import hashlib
import os
import sys
from typing import Any

_RERANKER_CACHE: Any = None
_RERANKER_LOAD_ATTEMPTED = False
_SCORE_CACHE: dict[str, float] = {}


def rerank_mode() -> str:
    mode = os.environ.get("OMNIX_GRAPHRAG_RERANK_MODE", "off").strip().lower()
    if mode not in {"on", "off", "auto"}:
        mode = "off"
    return mode


def _load_reranker() -> Any:
    global _RERANKER_CACHE, _RERANKER_LOAD_ATTEMPTED
    if _RERANKER_CACHE is not None:
        return _RERANKER_CACHE
    if _RERANKER_LOAD_ATTEMPTED:
        return None
    _RERANKER_LOAD_ATTEMPTED = True
    try:
        from sentence_transformers import CrossEncoder  # type: ignore[import-untyped]

        _RERANKER_CACHE = CrossEncoder("BAAI/bge-reranker-v2-m3", max_length=512)
        return _RERANKER_CACHE
    except Exception as exc:  # pragma: no cover - depends on local model availability
        print(f"[omnix] bge-reranker load failed: {exc}", file=sys.stderr)
        return None


def _cache_key(query: str, doc: str) -> str:
    h = hashlib.sha256()
    h.update(query.encode("utf-8", errors="replace"))
    h.update(b"\x00")
    h.update(doc.encode("utf-8", errors="replace"))
    return h.hexdigest()


def rerank(query: str, docs: list[str], top_n: int = 10) -> list[tuple[int, float]]:
    mode = rerank_mode()
    if mode == "off":
        return [(idx, 0.0) for idx in range(min(top_n, len(docs)))]
    model = _load_reranker()
    if model is None:
        if mode == "on":
            raise RuntimeError("OMNIX_GRAPHRAG_RERANK_MODE=on but reranker unavailable")
        return [(idx, 0.0) for idx in range(min(top_n, len(docs)))]

    pairs: list[list[str]] = []
    pair_indices: list[tuple[int, str]] = []
    scored: dict[int, float] = {}
    for idx, doc in enumerate(docs):
        key = _cache_key(query, doc)
        if key in _SCORE_CACHE:
            scored[idx] = _SCORE_CACHE[key]
        else:
            pairs.append([query, doc])
            pair_indices.append((idx, key))
    if pairs:
        scores = model.predict(pairs)
        for (idx, key), score in zip(pair_indices, scores, strict=True):
            scored[idx] = float(score)
            _SCORE_CACHE[key] = float(score)
    return sorted(scored.items(), key=lambda item: item[1], reverse=True)[:top_n]
