# CLASSIFICATION: XFAIL-WITH-REASON — all 10 tests reference /action/dispatch route + omnix.studio.server.get_provider_client (slice 15.3.7 action-dispatch backend not yet built)
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from omnix.graph.store import GraphStore
from omnix.studio.server import app
from omnix.studio.workspace import MANAGER, Workspace

pytestmark = pytest.mark.xfail(
    strict=True,
    reason=(
        "slice 15.3.7 action-dispatch backend: omnix.studio.server lacks the "
        "/action/dispatch route and the get_provider_client symbol that these "
        "tests monkeypatch. Whole module marked xfail-strict until slice 15.3.7 "
        "lands the backend. Tracked as a known pre-M1 limitation. "
        "[Outside M1 finisher Phase 4-7 scope — separate slice-15.3.7 work stream.]"
    ),
)


def _client(tmp_path: Path, monkeypatch: Any) -> TestClient:
    monkeypatch.setenv("HOME", str(tmp_path))
    return TestClient(app)


class _FakeClient:
    provider = "anthropic"

    def chat(
        self, messages: list[dict[str, str]], model: str | None = None, **_: Any
    ) -> dict[str, Any]:
        joined = "\n".join(m["content"] for m in messages)
        return {
            "ok": True,
            "content": "fake answer",
            "provider": "anthropic",
            "model": model or "claude-test",
            "usage": {"tokens_in": len(joined.split()), "tokens_out": 2},
            "receipt_path": "receipt-123",
        }


class _RecordingClient(_FakeClient):
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] = {}

    def chat(
        self, messages: list[dict[str, str]], model: str | None = None, **kwargs: Any
    ) -> dict[str, Any]:
        self.kwargs = kwargs
        return super().chat(messages, model=model, **kwargs)


class _ErrorClient:
    provider = "openai"

    def chat(
        self, messages: list[dict[str, str]], model: str | None = None, **_: Any
    ) -> dict[str, Any]:
        return {
            "ok": False,
            "error": "provider_error",
            "error_class": "provider_error",
            "error_message": "OpenAI: Incorrect API key provided (401)",
            "http_status": 401,
            "provider": "openai",
            "model": model or "gpt-test",
            "retryable": False,
            "usage": {"tokens_in": 0, "tokens_out": 0},
            "latency_ms": 12,
            "receipt_path": "receipt-error",
        }


def test_action_dispatch_route_localhost_only(tmp_path: Path, monkeypatch: Any) -> None:
    c = _client(tmp_path, monkeypatch)
    r = c.post(
        "/api/action/dispatch",
        json={"descriptor_id": "x", "prompt": "hello", "provider": "anthropic"},
        headers={"Host": "evil.com"},
    )
    assert r.status_code == 403


def test_action_dispatch_no_key_returns_400(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setattr("omnix.studio.server.get_provider_client", lambda *_a, **_k: None)
    c = _client(tmp_path, monkeypatch)
    r = c.post(
        "/api/action/dispatch",
        json={"descriptor_id": "x", "prompt": "hello", "provider": "anthropic"},
    )
    assert r.status_code == 400
    assert r.json()["error"] == "no_key_registered"
    assert r.json()["provider"] == "anthropic"


def test_action_dispatch_prompt_cap(tmp_path: Path, monkeypatch: Any) -> None:
    c = _client(tmp_path, monkeypatch)
    r = c.post(
        "/api/action/dispatch",
        json={"descriptor_id": "x", "prompt": "x" * 50_001, "provider": "anthropic"},
    )
    assert r.status_code == 413


def test_action_dispatch_plain_passes_through_provider(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        "omnix.studio.server.get_provider_client", lambda *_a, **_k: _FakeClient()
    )
    c = _client(tmp_path, monkeypatch)
    r = c.post(
        "/api/action/dispatch",
        json={
            "descriptor_id": "xray.agent.explain_selection",
            "prompt": "explain without raw logs",
            "provider": "anthropic",
            "model": "claude-test",
            "project_id": "proj",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["text"] == "fake answer"
    assert body["provider"] == "anthropic"
    assert body["model"] == "claude-test"
    assert body["tokens_in"] > 0


def test_action_dispatch_route_passes_provider_override(
    tmp_path: Path, monkeypatch: Any
) -> None:
    fake = _RecordingClient()
    monkeypatch.setattr("omnix.studio.server.get_provider_client", lambda *_a, **_k: fake)
    c = _client(tmp_path, monkeypatch)
    r = c.post(
        "/api/action/dispatch",
        json={
            "descriptor_id": "xray.agent.explain_selection",
            "prompt": "explain",
            "provider": "openai",
            "model": "gpt-test",
            "project_id": "proj",
        },
    )
    assert r.status_code == 200
    assert fake.kwargs["provider_override"] == "openai"


def test_action_dispatch_tools_require_workspace_id(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        "omnix.studio.server.get_provider_client", lambda *_a, **_k: _FakeClient()
    )
    c = _client(tmp_path, monkeypatch)
    r = c.post(
        "/api/action/dispatch",
        json={
            "descriptor_id": "xray.agent.explain_selection",
            "prompt": "explain",
            "provider": "anthropic",
            "project_id": "proj",
            "tools": ["find_callers"],
        },
    )
    assert r.status_code == 422
    assert "workspace_id" in r.json()["detail"]


def test_action_dispatch_tool_reads_graph_store(
    tmp_path: Path, monkeypatch: Any
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    store = GraphStore(str(tmp_path / "graph.db"))
    store.add_node("a.py::foo", "foo", "function", "a.py", 1, 5)
    store.add_node("b.py::bar", "bar", "function", "b.py", 10, 12)
    store.add_edge("b.py::bar", "a.py::foo", "CALLS")
    store.commit()
    workspace = Workspace("wid-tools", project, "existing", store, __import__("asyncio").Event())
    MANAGER.put(workspace)
    monkeypatch.setattr(
        "omnix.studio.server.get_provider_client", lambda *_a, **_k: _FakeClient()
    )
    c = _client(tmp_path, monkeypatch)
    try:
        r = c.post(
            "/api/action/dispatch",
            json={
                "descriptor_id": "xray.agent.explain_selection",
                "prompt": "explain",
                "provider": "anthropic",
                "project_id": "proj",
                "workspace_id": "wid-tools",
                "tools": ["find_callers"],
                "tool_args": {"node_id": "a.py::foo"},
            },
        )
    finally:
        MANAGER.remove("wid-tools")
        store.close()
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["tool_steps"][0]["tool"] == "find_callers"
    assert "bar" in json.dumps(body["tool_steps"])


def test_action_dispatch_ollama_graceful_degradation(
    tmp_path: Path, monkeypatch: Any
) -> None:
    fake = _FakeClient()
    fake.provider = "ollama"
    monkeypatch.setattr("omnix.studio.server.get_provider_client", lambda *_a, **_k: fake)
    c = _client(tmp_path, monkeypatch)
    r = c.post(
        "/api/action/dispatch",
        json={
            "descriptor_id": "rightrail.new_agent",
            "prompt": "summarize",
            "provider": "ollama",
            "project_id": "proj",
            "workspace_id": "missing-is-ok-for-ollama-degrade",
            "tools": ["read_code_region"],
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    assert body["tool_steps"][0]["status"] == "degraded"


def test_action_dispatch_audit_log_has_no_content(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        "omnix.studio.server.get_provider_client", lambda *_a, **_k: _FakeClient()
    )
    c = _client(tmp_path, monkeypatch)
    r = c.post(
        "/api/action/dispatch",
        json={
            "descriptor_id": "x",
            "prompt": "SECRET PROMPT CONTENT",
            "provider": "anthropic",
            "project_id": "proj",
        },
    )
    assert r.status_code == 200
    log = tmp_path / ".omnix" / "audit" / "action_dispatches.log"
    assert log.exists()
    text = log.read_text()
    assert "SECRET PROMPT CONTENT" not in text
    assert "fake answer" not in text
    row = json.loads(text.splitlines()[-1])
    assert row["descriptor_id"] == "x"
    assert "prompt" not in row
    assert "response" not in row


def test_action_dispatch_error_detail_serialized_without_audit_content(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setattr(
        "omnix.studio.server.get_provider_client", lambda *_a, **_k: _ErrorClient()
    )
    c = _client(tmp_path, monkeypatch)
    r = c.post(
        "/api/action/dispatch",
        json={
            "descriptor_id": "x",
            "prompt": "SECRET PROMPT CONTENT",
            "provider": "openai",
            "model": "gpt-test",
            "project_id": "proj",
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is False
    assert body["error_class"] == "provider_error"
    assert body["error_message"] == "OpenAI: Incorrect API key provided (401)"
    assert body["http_status"] == 401
    assert body["retryable"] is False

    log = tmp_path / ".omnix" / "audit" / "action_dispatches.log"
    row = json.loads(log.read_text().splitlines()[-1])
    assert row["error_class"] == "provider_error"
    assert row["http_status"] == 401
    assert "error_message" not in row
    assert "body_text" not in row
    assert "body_json" not in row
    assert "prompt" not in row
