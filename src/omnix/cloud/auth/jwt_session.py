"""JWT session tokens.

Algorithm: HS256 by default (using OMNIX_JWT_SECRET).
For production rotation, swap to RS256 with a JWKS endpoint published at /v1/auth/.well-known/jwks.json.
Sessions encode:
  sub          user_id
  tenant       tenant_id
  tier         tenant tier
  email        user email
  scope        space-separated scopes
  iat / exp    issued / expiry
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from typing import Any

import jwt

from omnix.cloud.config import get_settings


class SessionError(RuntimeError):
    pass


@dataclass
class Session:
    user_id: str
    tenant_id: str
    tier: str
    email: str
    scopes: tuple[str, ...]
    issued_at: int
    expires_at: int
    jti: str


def issue(user_id: str, tenant_id: str, tier: str, email: str,
          *, scopes: tuple[str, ...] = (), ttl_seconds: int | None = None) -> str:
    settings = get_settings()
    now = int(time.time())
    exp = now + (ttl_seconds or settings.session_ttl_seconds)
    payload = {
        "sub": user_id,
        "tenant": tenant_id,
        "tier": tier,
        "email": email,
        "scope": " ".join(scopes),
        "iat": now,
        "exp": exp,
        "jti": uuid.uuid4().hex,
        "iss": "omnix.cloud",
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def verify(token: str) -> Session:
    settings = get_settings()
    try:
        claims: dict[str, Any] = jwt.decode(
            token, settings.jwt_secret, algorithms=["HS256"], options={"require": ["exp", "iat", "sub"]}
        )
    except jwt.PyJWTError as exc:
        raise SessionError(f"invalid session: {exc}") from exc

    return Session(
        user_id=claims["sub"],
        tenant_id=claims.get("tenant", ""),
        tier=claims.get("tier", "smb"),
        email=claims.get("email", ""),
        scopes=tuple((claims.get("scope") or "").split()) if claims.get("scope") else (),
        issued_at=int(claims.get("iat", 0)),
        expires_at=int(claims["exp"]),
        jti=claims.get("jti", ""),
    )
