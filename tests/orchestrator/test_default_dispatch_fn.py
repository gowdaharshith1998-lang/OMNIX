"""Unit tests for `omnix.orchestrator.dispatcher._default_dispatch_fn`.

Covers the production-side wiring without making real LLM calls:
  - Provider routing by model id
  - Vault-miss error path
  - Fabric ok=False error path
  - Fabric non-dict / non-string content error paths
  - Happy path with a credentialed stub client

Real-LLM integration test lives in `test_e2e_real_dispatch.py`, gated by
`OMNIX_REAL_LLM=1`.
"""

from __future__ import annotations

from typing import Any

import pytest

from omnix.orchestrator.dispatcher import (
    OrchestratorError,
    _default_dispatch_fn,
    _provider_for_model,
)

# ----- Provider routing ----------------------------------------------------


@pytest.mark.parametrize(
    "model,expected",
    [
        ("claude-opus-4.7", "anthropic"),
        ("claude-3-5-sonnet-latest", "anthropic"),
        ("anthropic/claude-haiku", "anthropic"),
        ("gpt-4o", "openai"),
        ("gpt-4-turbo", "openai"),
        ("o1-mini", "openai"),
        ("o3-pro", "openai"),
        ("openai/gpt-4", "openai"),
        ("gemini-1.5-pro", "google"),
        ("google/gemini-flash", "google"),
        ("ollama/llama3", "ollama"),
        ("unknown-model-9000", "anthropic"),  # default fallback
    ],
)
def test_provider_for_model_routes_correctly(model: str, expected: str) -> None:
    assert _provider_for_model(model) == expected


def test_provider_for_model_is_case_insensitive_and_strips_whitespace() -> None:
    assert _provider_for_model("  CLAUDE-OPUS-4.7  ") == "anthropic"
    assert _provider_for_model("GPT-4o") == "openai"


# ----- _default_dispatch_fn ------------------------------------------------


@pytest.fixture
def _no_key_registered(monkeypatch: pytest.MonkeyPatch) -> None:
    """Vault has no key for any provider."""
    import omnix.providers.client as client_mod

    monkeypatch.setattr(
        client_mod,
        "get_provider_client",
        lambda provider_name, project_id=None: None,
    )


def test_default_dispatch_fn_raises_orchestrator_error_when_vault_has_no_key(
    _no_key_registered: None,
) -> None:
    with pytest.raises(OrchestratorError, match="no API key registered"):
        _default_dispatch_fn("hello", model="claude-opus-4.7")


def test_default_dispatch_fn_error_message_names_the_inferred_provider(
    _no_key_registered: None,
) -> None:
    with pytest.raises(OrchestratorError, match="'openai'"):
        _default_dispatch_fn("hello", model="gpt-4o")


class _StubClient:
    """In-memory CallableProviderClient stand-in for tests."""

    def __init__(self, response: Any) -> None:
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        self.calls.append({"messages": messages, **kwargs})
        return self._response


def _install_stub_client(
    monkeypatch: pytest.MonkeyPatch, response: Any
) -> _StubClient:
    stub = _StubClient(response)
    import omnix.orchestrator.dispatcher as dm

    # _default_dispatch_fn imports lazily from omnix.providers.client.
    # Patch the module attribute the lazy import will resolve.
    import omnix.providers.client as client_mod

    monkeypatch.setattr(
        client_mod,
        "get_provider_client",
        lambda provider_name, project_id=None: stub,
    )
    # Suppress unused-variable lint
    _ = dm
    return stub


def test_default_dispatch_fn_happy_path_returns_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stub = _install_stub_client(
        monkeypatch,
        {"ok": True, "content": "public class T {}", "model": "claude-opus-4.7"},
    )
    result = _default_dispatch_fn("rebuild this", model="claude-opus-4.7")
    assert result == "public class T {}"
    assert len(stub.calls) == 1
    assert stub.calls[0]["messages"] == [{"role": "user", "content": "rebuild this"}]
    assert stub.calls[0]["model"] == "claude-opus-4.7"
    assert stub.calls[0]["task_kind"] == "rebuild"
    assert stub.calls[0]["agent_id"] == "omnix-orchestrator"


def test_default_dispatch_fn_raises_on_fabric_ok_false_with_error_message(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub_client(
        monkeypatch,
        {
            "ok": False,
            "error_message": "Incorrect API key provided",
            "provider": "anthropic",
            "http_status": 401,
        },
    )
    with pytest.raises(
        OrchestratorError, match="Incorrect API key provided"
    ) as exc:
        _default_dispatch_fn("hello", model="claude-opus-4.7")
    # The error message should surface the provider + http_status for triage.
    assert "anthropic" in str(exc.value)
    assert "401" in str(exc.value)


def test_default_dispatch_fn_raises_on_non_dict_fabric_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub_client(monkeypatch, "not-a-dict")
    with pytest.raises(OrchestratorError, match="non-dict result"):
        _default_dispatch_fn("hello", model="claude-opus-4.7")


def test_default_dispatch_fn_raises_on_non_string_content(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_stub_client(monkeypatch, {"ok": True, "content": 42})
    with pytest.raises(OrchestratorError, match="non-string content"):
        _default_dispatch_fn("hello", model="claude-opus-4.7")
