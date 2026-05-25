"""Cloud-side configuration loaded from environment.

Single source of truth for service URLs, secrets, and feature flags.
Never reach into the core CLI's config — keep the surfaces independent.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from functools import lru_cache


def _env(name: str, default: str | None = None, *, required: bool = False) -> str | None:
    value = os.environ.get(name, default)
    if required and not value:
        raise RuntimeError(f"Required environment variable not set: {name}")
    return value


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class CloudSettings:
    env: str = field(default_factory=lambda: _env("OMNIX_CLOUD_ENV", "dev") or "dev")

    database_url: str = field(
        default_factory=lambda: _env(
            "OMNIX_DATABASE_URL",
            "postgresql+asyncpg://omnix:omnix@localhost:5432/omnix",
        )
        or "postgresql+asyncpg://omnix:omnix@localhost:5432/omnix"
    )
    sync_database_url: str = field(
        default_factory=lambda: _env(
            "OMNIX_SYNC_DATABASE_URL",
            "postgresql+psycopg://omnix:omnix@localhost:5432/omnix",
        )
        or "postgresql+psycopg://omnix:omnix@localhost:5432/omnix"
    )

    redis_url: str = field(
        default_factory=lambda: _env("OMNIX_REDIS_URL", "redis://localhost:6379/0")
        or "redis://localhost:6379/0"
    )

    storage_backend: str = field(
        default_factory=lambda: _env("OMNIX_STORAGE_BACKEND", "r2") or "r2"
    )
    storage_bucket: str = field(
        default_factory=lambda: _env("OMNIX_STORAGE_BUCKET", "omnix-uploads")
        or "omnix-uploads"
    )
    storage_endpoint: str | None = field(
        default_factory=lambda: _env("OMNIX_STORAGE_ENDPOINT", None)
    )
    storage_region: str = field(
        default_factory=lambda: _env("OMNIX_STORAGE_REGION", "auto") or "auto"
    )

    tus_data_dir: str = field(
        default_factory=lambda: _env("OMNIX_TUS_DATA_DIR", "/tmp/omnix-tus")
        or "/tmp/omnix-tus"
    )
    tus_max_bytes: int = field(
        default_factory=lambda: int(
            _env("OMNIX_TUS_MAX_BYTES", str(100 * 1024 * 1024 * 1024)) or "0"
        )
    )

    git_clone_max_bytes: int = field(
        default_factory=lambda: int(
            _env("OMNIX_GIT_CLONE_MAX_BYTES", str(5 * 1024 * 1024 * 1024)) or "0"
        )
    )

    workos_api_key: str | None = field(
        default_factory=lambda: _env("WORKOS_API_KEY", None)
    )
    workos_client_id: str | None = field(
        default_factory=lambda: _env("WORKOS_CLIENT_ID", None)
    )
    jwt_secret: str = field(
        default_factory=lambda: _env("OMNIX_JWT_SECRET", "dev-only-secret")
        or "dev-only-secret"
    )
    session_ttl_seconds: int = field(
        default_factory=lambda: int(_env("OMNIX_SESSION_TTL_SECONDS", "28800") or "0")
    )

    receipt_signing_key_path: str | None = field(
        default_factory=lambda: _env("OMNIX_SIGN_KEY_PATH", None)
    )
    receipt_verify_key_path: str | None = field(
        default_factory=lambda: _env("OMNIX_VERIFY_KEY_PATH", None)
    )

    cloud_api_base_url: str = field(
        default_factory=lambda: _env(
            "OMNIX_CLOUD_API_BASE_URL", "http://localhost:8080"
        )
        or "http://localhost:8080"
    )
    verifier_base_url: str = field(
        default_factory=lambda: _env(
            "OMNIX_VERIFIER_BASE_URL", "http://localhost:8090"
        )
        or "http://localhost:8090"
    )

    github_app_webhook_secret: str | None = field(
        default_factory=lambda: _env("OMNIX_GITHUB_APP_WEBHOOK_SECRET", None)
    )

    sentry_dsn: str | None = field(default_factory=lambda: _env("SENTRY_DSN", None))

    debug: bool = field(default_factory=lambda: _env_bool("OMNIX_DEBUG", False))


@lru_cache(maxsize=1)
def get_settings() -> CloudSettings:
    return CloudSettings()
