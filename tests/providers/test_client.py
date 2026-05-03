from __future__ import annotations

from pathlib import Path
from typing import Any

from axiom import provider_vault
from providers.client import get_provider_client


def test_get_provider_client_returns_none_without_key(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    assert get_provider_client("openai") is None


def test_provider_client_dispatches_with_vault_key(
    tmp_path: Path, monkeypatch: Any
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(provider_vault, "_keyring_module", lambda: None)
    provider_vault.encrypt_key("openai", "sk-client", "global")
    seen: dict[str, Any] = {}

    def fake_dispatch(data: dict[str, Any]) -> dict[str, Any]:
        seen.update(data)
        return {"ok": True}

    monkeypatch.setattr("providers.client.dispatch", fake_dispatch)
    client = get_provider_client("openai")
    assert client is not None
    assert client.chat([{"role": "user", "content": "hi"}]) == {"ok": True}
    assert seen["provider_key"] == {"provider": "openai", "key": "sk-client"}
