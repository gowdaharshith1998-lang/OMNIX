from __future__ import annotations

from typing import Any
from unittest import mock

from fabric import config as fc, dispatcher
from providers.registry import PROVIDERS
from tests.fabric import mocks


def test_valid_providers_are_dynamic() -> None:
    assert set(dispatcher._VALID) == set(PROVIDERS)


@mock.patch("fabric.providers.common.urllib.request.urlopen")
def test_openai_compatible_uses_provider_base_url(m_url: Any, tmp_path: Any) -> None:
    m_url.return_value = mocks.openai_ok("groq", 1, 1)
    cfgp = tmp_path / "fabric_config.json"
    cfg = fc.default_config()
    cfg["default_chain"] = ["groq"]
    cfg["default_models"]["groq"] = "llama-3.3-70b-versatile"
    fc.save_config(cfg, cfgp)
    out = dispatcher.dispatch(
        {
            "agent_id": "a",
            "task_kind": "debug",
            "messages": [{"role": "user", "content": "hi"}],
            "provider_key": {"provider": "groq", "key": "gsk"},
            "options": {"provider_override": "groq"},
        },
        config_path=cfgp,
    )
    assert out["ok"] is True
    req = m_url.call_args[0][0]
    assert "api.groq.com/openai/v1/chat/completions" in req.full_url


@mock.patch("fabric.providers.common.urllib.request.urlopen")
def test_custom_provider_uses_custom_base_url(m_url: Any, tmp_path: Any) -> None:
    m_url.return_value = mocks.openai_ok("custom", 1, 1)
    cfgp = tmp_path / "fabric_config.json"
    cfg = fc.default_config()
    cfg["default_chain"] = ["custom"]
    fc.save_config(cfg, cfgp)
    out = dispatcher.dispatch(
        {
            "agent_id": "a",
            "task_kind": "debug",
            "messages": [{"role": "user", "content": "hi"}],
            "provider_key": {"provider": "custom", "key": "ck"},
            "options": {
                "provider_override": "custom",
                "model_override": "local-model",
                "custom_base_url": "http://localhost:8000/v1",
            },
        },
        config_path=cfgp,
    )
    assert out["ok"] is True
    req = m_url.call_args[0][0]
    assert req.full_url == "http://localhost:8000/v1/chat/completions"
