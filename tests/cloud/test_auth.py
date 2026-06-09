"""Auth + tenancy tests using the stub identity provider."""

from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from omnix.cloud.api.main import create_app
from omnix.cloud.auth.jwt_session import SessionError, issue, verify
from omnix.cloud.auth.workos import StubProvider, set_provider


@pytest.fixture
def client():
    set_provider(StubProvider())
    yield TestClient(create_app())
    set_provider(None)


def test_issue_and_verify_session():
    token = issue("u-1", "t-1", "smb", "x@y.com", scopes=("read", "write"))
    sess = verify(token)
    assert sess.user_id == "u-1"
    assert sess.tenant_id == "t-1"
    assert sess.tier == "smb"
    assert sess.scopes == ("read", "write")


def test_verify_rejects_tampered_token():
    token = issue("u-1", "t-1", "smb", "x@y.com")
    bad = token[:-2] + ("AA" if not token.endswith("AA") else "BB")
    with pytest.raises(SessionError):
        verify(bad)


def test_verify_rejects_expired_token():
    token = issue("u-1", "t-1", "smb", "x@y.com", ttl_seconds=-10)
    with pytest.raises(SessionError):
        verify(token)


def test_login_redirects_to_workos(client):
    resp = client.get("/v1/auth/login", params={"redirect_uri": "http://localhost/cb"},
                      follow_redirects=False)
    assert resp.status_code == 303
    assert "code=" in resp.headers["location"]


def test_callback_mints_session(client):
    code = "stub:user-42:hello@bank.com:org-bank-acme"
    resp = client.get(
        "/v1/auth/callback",
        params={"code": code, "state": "state-1"},
        cookies={"omnix_state": "state-1"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["tier"] == "banking"
    assert body["tenant_id"] == "org-bank-acme"
    assert body["email"] == "hello@bank.com"

    me = client.get("/v1/auth/me", headers={"Authorization": f"Bearer {body['token']}"})
    assert me.status_code == 200


def test_callback_rejects_missing_state_cookie(client):
    code = "stub:user-42:hello@bank.com:org-bank-acme"
    resp = client.get("/v1/auth/callback", params={"code": code, "state": "state-1"})
    assert resp.status_code == 400


def test_callback_rejects_tenant_hint_mismatch(client):
    code = "stub:user-42:hello@bank.com:org-bank-acme"
    resp = client.get(
        "/v1/auth/callback",
        params={"code": code, "state": "state-1"},
        cookies={"omnix_state": "state-1"},
        headers={"X-Tenant-Id-Hint": "attacker-tenant"},
    )
    assert resp.status_code == 403


def test_me_requires_bearer(client):
    resp = client.get("/v1/auth/me")
    assert resp.status_code == 401


def test_protected_route_rejects_bad_token(client):
    # Use jobs route; bad token should 401 via middleware
    resp = client.get("/v1/jobs/some-id",
                      headers={"Authorization": "Bearer not-a-jwt"})
    assert resp.status_code == 401


def test_cross_tenant_enforcement_blocks_access():
    from omnix.cloud.auth.jwt_session import Session
    from omnix.cloud.auth.tenancy import (
        CrossTenantAccessError,
        _current_session,
        enforce_tenant,
    )

    sess = Session(user_id="u", tenant_id="tenant-A", tier="smb",
                   email="x@y", scopes=(), issued_at=int(time.time()),
                   expires_at=int(time.time()) + 3600, jti="j")
    tok = _current_session.set(sess)
    try:
        # same tenant ok
        enforce_tenant("tenant-A")
        # different tenant blocked
        with pytest.raises(CrossTenantAccessError):
            enforce_tenant("tenant-B")
    finally:
        _current_session.reset(tok)
