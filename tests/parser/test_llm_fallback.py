"""LLM graph fallback: fabric mocks, no real providers (ITER 3)."""

from __future__ import annotations

from unittest import mock

import pytest

from fabric import dispatcher
from src.graph.store import GraphStore
from src.parser import llm_fallback

_JSON = (
    '{"functions":[{"name":"f","line":2,"params":["a"]}],"classes":[],'
    '"calls":[],"imports":["x"]}'
)


def _ok_dispatch_content() -> dict:
    return {
        "ok": True,
        "content": _JSON,
        "call_id": "c1",
        "provider": "ollama",
        "model": "m",
        "usage": {"tokens_in": 1, "tokens_out": 2},
    }


@pytest.fixture
def gstore() -> GraphStore:
    s = GraphStore(":memory:")
    s.add_node(
        id="x.txt",
        name="x",
        type="file",
        file_path="x.txt",
        start_line=1,
        end_line=10,
        complexity=0,
    )
    yield s
    s.close()


def test_llm_fallback_triggered_below_threshold(gstore: GraphStore) -> None:
    llm_fallback.reset_llm_fallback_budget_for_tests()
    llm_fallback.set_llm_fallback_remaining_for_tests(5)
    with mock.patch.object(
        dispatcher, "dispatch", return_value=_ok_dispatch_content()
    ) as m:
        r = llm_fallback.try_llm_fallback(
            gstore,
            "x.txt",
            "0\n1\n2\n3\n4\n" * 2,  # >=5 lines, short content
            quality_score=0.1,
            language="d",
            provider_key={"provider": "ollama", "key": "k"},
        )
    assert m.called
    assert r.called_llm is True
    assert r.parse_mode == "llm"
    fn = {n.id for n in gstore.get_all_nodes() if n.name == "f" and n.type == "function"}
    assert f"x.txt::f" in fn
    fnode = next(
        n for n in gstore.get_all_nodes() if n.id == "x.txt::f" and n.type == "function"
    )
    assert fnode.metadata
    assert fnode.metadata.get("source") == "llm"
    im = next(n for n in gstore.get_all_nodes() if n.type == "import" and "x" in n.name)
    assert im.metadata
    assert im.metadata.get("source") == "llm"


def test_llm_fallback_skipped_above_threshold(gstore: GraphStore) -> None:
    """High quality: no LLM. P12: very short file uses parse_mode=empty, no call."""
    llm_fallback.reset_llm_fallback_budget_for_tests()
    llm_fallback.set_llm_fallback_remaining_for_tests(5)
    with mock.patch.object(dispatcher, "dispatch") as m:
        r1 = llm_fallback.try_llm_fallback(
            gstore,
            "a.txt",
            "line\n" * 6,
            quality_score=0.8,
            language="d",
            provider_key={"provider": "ollama", "key": "k"},
        )
    assert r1.parse_mode == "no_llm"
    assert r1.called_llm is False
    assert not m.called

    with mock.patch.object(dispatcher, "dispatch") as m2:
        r2 = llm_fallback.try_llm_fallback(
            gstore,
            "b.txt",
            "a\nb",
            quality_score=0.1,
            language="d",
            provider_key={"provider": "ollama", "key": "k"},
        )
    assert r2.quality_score == 0.0
    assert r2.parse_mode == "empty"
    assert r2.called_llm is False
    assert not m2.called


def test_llm_fallback_budget_respected(
    gstore: GraphStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv(llm_fallback.ENV_BUDGET, "2")
    llm_fallback.reset_llm_fallback_budget_for_tests()
    with mock.patch.object(
        dispatcher, "dispatch", return_value=_ok_dispatch_content()
    ) as m:
        for k in (1, 2, 3):
            gstore.add_node(
                id=f"run_{k}.txt",
                name=f"run_{k}.txt",
                type="file",
                file_path=f"run_{k}.txt",
                start_line=1,
                end_line=10,
                complexity=0,
            )
            llm_fallback.try_llm_fallback(
                gstore,
                f"run_{k}.txt",
                "0\n" * 6,
                quality_score=0.05,
                language="d",
                provider_key={"provider": "ollama", "key": "k"},
            )
    assert m.call_count == 2
