"""Cloud-suite test fixtures.

Conventions:
  * No live Postgres/Redis required for unit tests — we monkeypatch the
    config and engines to sqlite/in-memory where possible.
  * Integration tests that need real infra are gated by env-marker
    `OMNIX_CLOUD_INTEGRATION=1` and skipped otherwise.
"""

from __future__ import annotations

import os
import tempfile

import pytest


@pytest.fixture(autouse=True)
def _cloud_env(monkeypatch, tmp_path):
    """Force every cloud test to a clean, isolated environment."""
    tus_dir = tmp_path / "tus"
    tus_dir.mkdir()
    monkeypatch.setenv("OMNIX_TUS_DATA_DIR", str(tus_dir))
    monkeypatch.setenv(
        "OMNIX_DATABASE_URL", "sqlite+aiosqlite:///:memory:"
    )
    monkeypatch.setenv(
        "OMNIX_SYNC_DATABASE_URL", "sqlite:///:memory:"
    )
    monkeypatch.setenv("OMNIX_REDIS_URL", "redis://localhost:6379/15")
    monkeypatch.setenv("OMNIX_DEBUG", "true")
    monkeypatch.setenv("OMNIX_STORAGE_BACKEND", "memory")
    monkeypatch.setenv("OMNIX_STORAGE_BUCKET", "omnix-test")
    monkeypatch.setenv("OMNIX_JWT_SECRET", "test-only-do-not-use-in-prod")

    # Clear the LRU caches that may have read prior env.
    from omnix.cloud.config import get_settings
    get_settings.cache_clear()
    try:
        from omnix.cloud.db.session import (
            get_async_engine,
            get_async_session_maker,
            get_sync_engine,
            get_sync_session_maker,
        )
        get_async_engine.cache_clear()
        get_async_session_maker.cache_clear()
        get_sync_engine.cache_clear()
        get_sync_session_maker.cache_clear()
    except Exception:
        pass


def integration_required():
    return pytest.mark.skipif(
        not os.environ.get("OMNIX_CLOUD_INTEGRATION"),
        reason="set OMNIX_CLOUD_INTEGRATION=1 to enable live-infra tests",
    )
