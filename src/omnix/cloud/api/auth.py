"""Authentication endpoints.

  GET  /v1/auth/login         redirect to WorkOS authorization URL
  GET  /v1/auth/callback      exchange code, mint session JWT
  POST /v1/auth/logout        invalidate session (revoke via jti — TODO denylist)
  GET  /v1/auth/me            return current session profile
"""

from __future__ import annotations

import secrets
from typing import Annotated

from fastapi import APIRouter, Cookie, Header, HTTPException, Query
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from omnix.cloud.auth.jwt_session import Session, SessionError, issue, verify
from omnix.cloud.auth.workos import get_provider
from omnix.cloud.config import get_settings

router = APIRouter()


def _cookie_secure() -> bool:
    """State cookies must be HTTPS-only in production; relaxed in dev so the
    OAuth round-trip works over plain http://localhost."""
    return not get_settings().debug


class AuthState(BaseModel):
    state: str
    redirect_to: str | None = None


@router.get("/login")
async def login(redirect_uri: str = Query(...), redirect_to: str | None = None):
    provider = get_provider()
    state = secrets.token_urlsafe(24)
    url = provider.authorization_url(redirect_uri=redirect_uri, state=state)
    resp = RedirectResponse(url, status_code=303)
    secure = _cookie_secure()
    resp.set_cookie("omnix_state", state, httponly=True, secure=secure, samesite="lax")
    if redirect_to:
        resp.set_cookie("omnix_post_auth", redirect_to, httponly=True,
                        secure=secure, samesite="lax")
    return resp


class CallbackResponse(BaseModel):
    token: str
    user_id: str
    tenant_id: str
    tier: str
    email: str


@router.get("/callback", response_model=CallbackResponse)
async def callback(
    code: str = Query(...),
    state: str | None = Query(None),
    omnix_state: str | None = Cookie(None),
    tenant_id_hint: str | None = Header(None, alias="X-Tenant-Id-Hint"),
):
    if not state or not omnix_state or not secrets.compare_digest(state, omnix_state):
        raise HTTPException(status_code=400, detail="invalid auth state")
    provider = get_provider()
    try:
        profile = provider.exchange_code(code)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail=f"code exchange failed: {exc}") from exc

    if tenant_id_hint and profile.workos_org_id and tenant_id_hint != profile.workos_org_id:
        raise HTTPException(status_code=403, detail="tenant hint does not match identity")
    tenant_id = profile.workos_org_id or "default"
    tier = "smb"
    if profile.workos_org_id and profile.workos_org_id.startswith("org-bank-"):
        tier = "banking"

    token = issue(
        user_id=profile.workos_user_id,
        tenant_id=tenant_id,
        tier=tier,
        email=profile.email,
    )
    return CallbackResponse(
        token=token,
        user_id=profile.workos_user_id,
        tenant_id=tenant_id,
        tier=tier,
        email=profile.email,
    )


@router.get("/me")
async def me(authorization: Annotated[str | None, Header()] = None):
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        sess: Session = verify(authorization.split(" ", 1)[1])
    except SessionError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    return {
        "user_id": sess.user_id,
        "tenant_id": sess.tenant_id,
        "tier": sess.tier,
        "email": sess.email,
        "scopes": list(sess.scopes),
        "expires_at": sess.expires_at,
    }
