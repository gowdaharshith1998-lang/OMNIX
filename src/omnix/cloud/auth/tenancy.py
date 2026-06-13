"""Tenant isolation enforcement.

Banking tier: database-per-tenant. Each tenant_id maps to a Postgres role +
schema; queries are routed to the tenant's dedicated database.
SMB / Team tier: shared schema. Every query MUST be qualified by tenant_id
via RLS or explicit predicate. We use a request-scoped middleware that
injects the tenant_id into a contextvar; data-access helpers read from it.
"""

from __future__ import annotations

import contextvars

from fastapi import HTTPException, Request

from omnix.cloud.auth.jwt_session import Session, SessionError, verify

_current_session: contextvars.ContextVar[Session | None] = contextvars.ContextVar(
    "omnix_current_session", default=None
)


def current_session() -> Session | None:
    return _current_session.get()


def current_tenant_id() -> str | None:
    s = current_session()
    return s.tenant_id if s else None


class TenancyMiddleware:
    """ASGI middleware that resolves the session from Authorization header.

    Anonymous requests (no header) pass through with no session set.
    Invalid tokens 401.
    The header value is also accepted via ``X-Omnix-Session`` for browser
    contexts where Authorization is reserved for upstream auth.
    """

    def __init__(self, app, *, public_paths: tuple[str, ...] = ("/health", "/version",
                                                                "/docs", "/openapi.json")) -> None:
        self.app = app
        self.public = public_paths

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        path = scope.get("path", "")
        if any(path == p or path.startswith(p + "/") for p in self.public):
            await self.app(scope, receive, send)
            return

        token = _extract_token(scope)
        if not token:
            await self.app(scope, receive, send)
            return
        try:
            session = verify(token)
        except SessionError:
            await _send_401(send)
            return
        tok_set = _current_session.set(session)
        try:
            await self.app(scope, receive, send)
        finally:
            _current_session.reset(tok_set)


def _extract_token(scope) -> str | None:
    for k, v in scope.get("headers", []):
        name = k.decode().lower()
        if name == "authorization":
            raw = v.decode()
            if raw.lower().startswith("bearer "):
                return raw.split(" ", 1)[1]
        if name == "x-omnix-session":
            return v.decode()
    return None


async def _send_401(send):
    body = b'{"detail":"invalid or expired session"}'
    await send({
        "type": "http.response.start",
        "status": 401,
        "headers": [(b"content-type", b"application/json"),
                    (b"content-length", str(len(body)).encode())],
    })
    await send({"type": "http.response.body", "body": body, "more_body": False})


def require_session(request: Request) -> Session:
    """FastAPI dependency."""
    sess = current_session()
    if sess is None:
        raise SessionError("no active session")
    return sess


def require_session_http() -> Session:
    """Return the request session or raise a FastAPI 401 response."""
    sess = current_session()
    if sess is None:
        raise HTTPException(status_code=401, detail="missing session")
    return sess


def require_session_tenant(x_tenant_id: str | None = None) -> str:
    """Return the authenticated tenant and reject spoofed tenant headers."""
    sess = require_session_http()
    if x_tenant_id and x_tenant_id != sess.tenant_id:
        raise HTTPException(status_code=403, detail="tenant header does not match session")
    return sess.tenant_id


class CrossTenantAccessError(RuntimeError):
    pass


def enforce_tenant(target_tenant_id: str) -> None:
    """Raise CrossTenantAccessError if the current session is for a different tenant."""
    sess = current_session()
    if sess is None or sess.tenant_id != target_tenant_id:
        raise CrossTenantAccessError(
            f"caller (tenant={sess.tenant_id if sess else None}) cannot access "
            f"resources of tenant {target_tenant_id}"
        )


def tenant_scoped_query_predicate() -> dict[str, str]:
    """Return a predicate dict callers can splice into SELECT clauses."""
    s = current_session()
    if s is None:
        raise CrossTenantAccessError("no session — cannot scope query")
    return {"tenant_id": s.tenant_id}
