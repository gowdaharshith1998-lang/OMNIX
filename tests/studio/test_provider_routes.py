from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi.testclient import TestClient

from omnix.receipts import provider_vault
from omnix.studio.server import app


def test_detect_route_does_not_persist(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    c = TestClient(app)
    r = c.post("/api/providers/detect", json={"raw_key": "sk-ant-fake"})
    assert r.status_code == 200
    assert r.json()["provider"] == "anthropic"
    assert provider_vault.list_keys() == []


def test_register_list_delete_provider_key(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setattr(provider_vault, "_keyring_module", lambda: None)
    c = TestClient(app)
    r = c.post(
        "/api/providers/keys",
        json={"raw_key": "gsk_secret1234", "scope": "global"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["provider"] == "groq"
    assert body["fingerprint"] == "1234"
    assert "gsk_secret1234" not in str(body)
    listed = c.get("/api/providers/keys").json()["keys"]
    assert listed and listed[0]["provider"] == "groq"
    d = c.delete(f"/api/providers/keys/{body['id']}")
    assert d.status_code == 200
    assert d.json()["deleted"] is True
    d2 = c.delete(f"/api/providers/keys/{body['id']}")
    assert d2.json() == {"deleted": False, "reason": "not_found"}


def test_custom_requires_base_url(tmp_path: Path, monkeypatch: Any) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    c = TestClient(app)
    r = c.post(
        "/api/providers/keys",
        json={"raw_key": "abc", "scope": "global", "override_provider": "custom"},
    )
    assert r.status_code == 422


def test_provider_routes_localhost_only() -> None:
    c = TestClient(app)
    r = c.post(
        "/api/providers/detect",
        json={"raw_key": "sk-ant-fake"},
        headers={"Host": "evil.com"},
    )
    assert r.status_code == 403
