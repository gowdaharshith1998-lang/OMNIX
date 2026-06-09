"""WorkOS AuthKit integration.

Three identity flows are supported:
  * SSO (SAML or OIDC) for enterprise tenants
  * Magic Link (passwordless) for SMB tenants
  * GitHub App identity for Shape C self-service

This module wraps a small Python SDK surface so tests can substitute a fake.
"""

from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Protocol

from omnix.cloud.config import get_settings


@dataclass
class IdentityProfile:
    workos_user_id: str
    email: str
    display_name: str | None
    workos_org_id: str | None
    connection_type: str  # "sso" | "magic_link" | "github"


class IdentityProvider(Protocol):
    def exchange_code(self, code: str) -> IdentityProfile: ...

    def authorization_url(self, *, redirect_uri: str, state: str,
                          connection_type: str = "sso") -> str: ...


class WorkOSProvider:
    def __init__(self) -> None:
        self.settings = get_settings()
        if not (self.settings.workos_api_key and self.settings.workos_client_id):
            raise RuntimeError(
                "WorkOS not configured: set WORKOS_API_KEY and WORKOS_CLIENT_ID"
            )
        try:
            import workos
        except ImportError as exc:  # pragma: no cover - prod path
            raise RuntimeError(
                "workos SDK not installed; pip install 'omnix[cloud]'"
            ) from exc
        workos.api_key = self.settings.workos_api_key
        workos.client_id = self.settings.workos_client_id
        self._workos = workos

    def authorization_url(self, *, redirect_uri: str, state: str,
                          connection_type: str = "sso") -> str:
        sso = self._workos.client.sso  # type: ignore[attr-defined]
        return sso.get_authorization_url(
            redirect_uri=redirect_uri,
            state=state,
            provider=connection_type,
            client_id=self.settings.workos_client_id,
        )

    def exchange_code(self, code: str) -> IdentityProfile:
        sso = self._workos.client.sso  # type: ignore[attr-defined]
        profile = sso.get_profile_and_token(code=code)
        return IdentityProfile(
            workos_user_id=profile.profile.id,
            email=profile.profile.email,
            display_name=getattr(profile.profile, "first_name", None),
            workos_org_id=getattr(profile.profile, "organization_id", None),
            connection_type="sso",
        )


class StubProvider:
    """Test/dev-only identity provider.

    The exchange_code call returns a deterministic profile derived from the
    code string itself. Format: ``stub:<user_id>:<email>:<org>``.
    """

    def authorization_url(self, *, redirect_uri: str, state: str,
                          connection_type: str = "sso") -> str:
        return f"{redirect_uri}?code=stub:test-user:test@example.com:org-1&state={state}"

    def exchange_code(self, code: str) -> IdentityProfile:
        if not code.startswith("stub:"):
            raise RuntimeError("stub provider only accepts 'stub:' codes")
        _, user_id, email, org = code.split(":", 3)
        return IdentityProfile(
            workos_user_id=user_id,
            email=email,
            display_name=email.split("@")[0],
            workos_org_id=org,
            connection_type="sso",
        )


_PROVIDER: IdentityProvider | None = None


def get_provider() -> IdentityProvider:
    global _PROVIDER
    if _PROVIDER is None:
        try:
            _PROVIDER = WorkOSProvider()
        except RuntimeError:
            settings = get_settings()
            allow_stub = (
                settings.env in {"dev", "test"}
                or os.environ.get("OMNIX_ALLOW_STUB_AUTH") == "1"
            )
            if not allow_stub:
                raise
            _PROVIDER = StubProvider()
    return _PROVIDER


def set_provider(provider: IdentityProvider | None) -> None:
    """Test hook — replace the resolved provider."""
    global _PROVIDER
    _PROVIDER = provider
