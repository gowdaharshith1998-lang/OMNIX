# CLASSIFICATION: MIXED — 1 PASSING (existing failover chain unchanged), 4 XFAIL (dispatcher.dispatch lacks provider_override kwarg — slice 15.3.7 backend feature)
from __future__ import annotations

from pathlib import Path
from typing import Any
from unittest import mock

import pytest

from omnix.fabric import budget, dedup, dispatcher, health, receipts, telemetry
from omnix.fabric import config as fc
from tests.fabric import mocks

_PROVIDER_OVERRIDE_XFAIL = pytest.mark.xfail(
    strict=True,
    reason=(
        "slice 15.3.7 LLM tool-dispatch: omnix.fabric.dispatcher.dispatch() does "
        "not yet accept a `provider_override` keyword argument. Test is the spec "
        "for slice 15.3.7's per-call provider pinning. Tracked in TODOS.md P1. "
        "[Outside M1 finisher Phase 4-7 scope — separate slice-15.3.7 work stream.]"
    ),
)


@pytest.fixture(autouse=True)
def fabric_reset(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Any:
    cfgp = tmp_path / "fabric_config.json"
    fc.save_config(fc.default_config(), cfgp)
    monkeypatch.setattr(fc, "CONFIG_PATH", cfgp)
    rdir = tmp_path / "receipts"
    rdir.mkdir(parents=True, exist_ok=True)
    receipts.set_paths_for_tests(receipt_dir=rdir, secret_path=tmp_path / "none.pem")
    budget.set_time_fn_for_tests(None)
    health.set_time_fn_for_tests(None)
    dispatcher.reset_runtime_for_tests()
    dedup.reset_for_tests()
    telemetry.reset_for_tests()
    yield
    receipts.reset_paths_for_tests()


def _payload(**kwargs: Any) -> dict[str, Any]:
    data = {
        "agent_id": "agent1",
        "task_kind": "debug",
        "messages": [{"role": "user", "content": "Say hello"}],
        "options": {"max_tokens": 50, "timeout_ms": 5000},
        "provider_key": {"provider": "anthropic", "key": "ak"},
    }
    data.update(kwargs)
    return data


@_PROVIDER_OVERRIDE_XFAIL
@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_provider_override_constrains_candidate_list(m_url: Any) -> None:
    def side_effect(req: Any, timeout: Any) -> Any:
        assert "api.openai.com" in req.full_url
        return mocks.openai_ok("openai-only", 2, 1)

    m_url.side_effect = side_effect
    out = dispatcher.dispatch(
        _payload(
            provider_key={"provider": "openai", "key": "ok"},
            provider_keys={"anthropic": "ak", "openai": "ok"},
        ),
        provider_override="openai",
    )
    assert out["ok"] is True
    assert out["provider"] == "openai"
    assert out["content"] == "openai-only"
    assert m_url.call_count == 1


@_PROVIDER_OVERRIDE_XFAIL
@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_provider_override_missing_key_returns_without_failover(m_url: Any) -> None:
    out = dispatcher.dispatch(_payload(), provider_override="openai")
    assert out["ok"] is False
    assert out["error_class"] == "missing_key"
    assert out["provider"] == "openai"
    assert m_url.call_count == 0


@_PROVIDER_OVERRIDE_XFAIL
@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_provider_override_transient_retries_same_provider_only(m_url: Any) -> None:
    m_url.side_effect = mocks.http_error(
        429, '{"error":{"message":"rate limited"}}'
    )
    out = dispatcher.dispatch(
        _payload(provider_key={"provider": "openai", "key": "ok"}),
        provider_override="openai",
    )
    assert out["ok"] is False
    assert out["error_class"] == "exhausted_retries"
    assert out["provider"] == "openai"
    assert out["http_status"] == 429
    assert out["retryable"] is True
    assert m_url.call_count == 3


@_PROVIDER_OVERRIDE_XFAIL
@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_provider_override_non_transient_error_returns_immediately(m_url: Any) -> None:
    m_url.side_effect = mocks.http_error(
        401, '{"error":{"message":"Incorrect API key provided"}}'
    )
    out = dispatcher.dispatch(
        _payload(provider_key={"provider": "openai", "key": "bad"}),
        provider_override="openai",
    )
    assert out["ok"] is False
    assert out["error_class"] == "provider_error"
    assert out["provider"] == "openai"
    assert out["http_status"] == 401
    assert out["retryable"] is False
    assert "Incorrect API key" in out["error_message"]
    assert m_url.call_count == 1


@mock.patch("omnix.fabric.providers.common.urllib.request.urlopen")
def test_without_provider_override_existing_failover_chain_remains(m_url: Any) -> None:
    calls = {"n": 0}

    def side_effect(req: Any, timeout: Any) -> Any:
        calls["n"] += 1
        if calls["n"] == 1:
            raise mocks.http_error(401, "{}")
        return mocks.openai_ok("from-openai", 2, 2)

    m_url.side_effect = side_effect
    out = dispatcher.dispatch(
        _payload(provider_keys={"anthropic": "ak", "openai": "ok"})
    )
    assert out["ok"] is True
    assert out["provider"] == "openai"
    assert out["content"] == "from-openai"

