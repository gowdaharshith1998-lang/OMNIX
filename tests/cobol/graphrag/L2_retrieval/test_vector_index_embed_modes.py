from __future__ import annotations

import builtins
import sys
import types
from typing import Any

import pytest

from omnix.retrieval import vector_index


def _reset_model_cache(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(vector_index, "_MODEL_CACHE", None)
    monkeypatch.setattr(vector_index, "_MODEL_LOAD_ATTEMPTED", False)


def test_hash_mode_uses_fallback_without_model_load(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_model_cache(monkeypatch)
    monkeypatch.setenv("OMNIX_GRAPHRAG_EMBED_MODE", "hash")

    vec = vector_index.embed_text("hello world")

    assert len(vec) == 384
    assert vector_index._MODEL_LOAD_ATTEMPTED is False


def test_auto_mode_falls_back_when_model_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_model_cache(monkeypatch)
    monkeypatch.setenv("OMNIX_GRAPHRAG_EMBED_MODE", "auto")
    expected = vector_index._embed_text_hash("hello world")

    original_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "sentence_transformers":
            raise ImportError("no model")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    assert vector_index.embed_text("hello world") == expected
    assert vector_index._MODEL_LOAD_ATTEMPTED is True


def test_auto_mode_uses_real_when_available(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_model_cache(monkeypatch)
    monkeypatch.setenv("OMNIX_GRAPHRAG_EMBED_MODE", "auto")

    class FakeModel:
        def encode(self, text: str, normalize_embeddings: bool = True) -> list[float]:
            assert text == "hello world"
            assert normalize_embeddings is True
            return [0.25] * 384

    module = types.ModuleType("sentence_transformers")
    module.SentenceTransformer = lambda _name: FakeModel()  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", module)

    vec = vector_index.embed_text("hello world")

    assert vec == [0.25] * 384
    assert vector_index._MODEL_LOAD_ATTEMPTED is True


def test_real_mode_raises_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_model_cache(monkeypatch)
    monkeypatch.setenv("OMNIX_GRAPHRAG_EMBED_MODE", "real")

    original_import = builtins.__import__

    def fake_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "sentence_transformers":
            raise ImportError("no model")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    with pytest.raises(RuntimeError, match="OMNIX_GRAPHRAG_EMBED_MODE=real"):
        vector_index.embed_text("hello world")


def test_hash_path_deterministic(monkeypatch: pytest.MonkeyPatch) -> None:
    _reset_model_cache(monkeypatch)
    monkeypatch.setenv("OMNIX_GRAPHRAG_EMBED_MODE", "hash")

    assert vector_index.embed_text("same input") == vector_index.embed_text("same input")
