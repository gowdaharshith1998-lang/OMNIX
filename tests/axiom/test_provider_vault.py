from __future__ import annotations

from pathlib import Path
from typing import Any

from axiom import provider_vault


def test_vault_file_fallback_roundtrip(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(provider_vault, "_keyring_module", lambda: None)
    meta = provider_vault.encrypt_key("openai", "sk-test-12345", "global")
    assert meta.fingerprint == "2345"
    assert provider_vault.decrypt_key("openai", "global") == "sk-test-12345"
    enc = tmp_path / ".omnix" / "providers" / "global" / "openai.enc"
    assert enc.is_file()
    assert "sk-test-12345" not in enc.read_text(encoding="utf-8")


def test_project_key_takes_precedence_over_global(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(provider_vault, "_keyring_module", lambda: None)
    provider_vault.encrypt_key("anthropic", "global-key", "global")
    provider_vault.encrypt_key("anthropic", "project-key", "project", "pid1")
    found = provider_vault.get_key("anthropic", "pid1")
    assert found is not None
    assert found.key == "project-key"
    assert found.metadata.scope == "project"


def test_delete_key_removes_metadata_and_ciphertext(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(provider_vault, "_keyring_module", lambda: None)
    meta = provider_vault.encrypt_key("groq", "gsk_secret", "global")
    assert provider_vault.delete_key_id(meta.id) is True
    assert provider_vault.get_key("groq") is None
    assert provider_vault.delete_key_id(meta.id) is False
