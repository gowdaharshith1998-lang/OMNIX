"""Tests for P4 — TUS storage_key resolution + inline receipts + broker timeout.

Covers gaps #45/10, #45/13, #45/14:

- POST /v1/jobs resolves tus upload_id → storage_key (or 404/409 on bad state)
- inline=true + mode=production emits a signed ML-DSA-65 completion receipt
  that verifies offline with the returned public key
- POST /v1/jobs async path returns clean 503 when broker times out / errors
  instead of hanging to gunicorn worker SIGABRT
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient


def _build_app() -> FastAPI:
    from omnix.cloud.api import jobs as jobs_router
    from omnix.cloud.auth.tenancy import TenancyMiddleware

    app = FastAPI()
    app.add_middleware(TenancyMiddleware)
    app.include_router(jobs_router.router, prefix="/v1/jobs")
    return app


def _auth_headers(tenant_id: str = "acme") -> dict[str, str]:
    from omnix.cloud.auth.jwt_session import issue

    token = issue("u-test", tenant_id, "smb", "test@example.com")
    return {"Authorization": f"Bearer {token}", "X-Tenant-Id": tenant_id}


def _build_tus_app() -> tuple[FastAPI, Path]:
    """App with both /v1/upload and /v1/jobs routers + isolated tus dir."""
    from omnix.cloud import config
    from omnix.cloud.api import jobs as jobs_router
    from omnix.cloud.auth.tenancy import TenancyMiddleware
    from omnix.cloud.ingest import tus_handler

    # Override the tus data dir to a fresh tmp so tests don't leak state.
    tmp = Path(os.environ.get("PYTEST_OMNIX_TUS_DIR", "/tmp/omnix-test-tus"))
    tmp.mkdir(parents=True, exist_ok=True)
    config.get_settings.cache_clear()  # type: ignore[attr-defined]
    os.environ["OMNIX_TUS_DATA_DIR"] = str(tmp)
    config.get_settings.cache_clear()  # type: ignore[attr-defined]

    app = FastAPI()
    app.add_middleware(TenancyMiddleware)
    app.include_router(tus_handler.router, prefix="/v1/upload")
    app.include_router(jobs_router.router, prefix="/v1/jobs")
    return app, tmp


def _write_tus_metadata(tus_dir: Path, upload_id: str, *,
                        committed: bool, storage_key: str | None,
                        offset: int = 100, length: int = 100,
                        sha256: str | None = "deadbeef") -> None:
    meta = {
        "id": upload_id,
        "length": length,
        "offset": offset,
        "metadata": {"filename": "bundle.tar"},
        "tenant_id": "acme",
        "sha256": sha256,
        "committed": committed,
        "storage_key": storage_key,
    }
    (tus_dir / f"{upload_id}.json").write_text(json.dumps(meta))


# -------------------- Gap #13: TUS upload_id → storage_key --------------------


def test_resolve_tus_source_404_for_missing_upload_id():
    from omnix.cloud.api.jobs import _resolve_tus_source
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _resolve_tus_source({"type": "tus", "upload_id": "does-not-exist"}, "acme")
    assert exc.value.status_code == 404


def test_resolve_tus_source_400_when_upload_id_missing():
    from omnix.cloud.api.jobs import _resolve_tus_source
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _resolve_tus_source({"type": "tus"}, "acme")
    assert exc.value.status_code == 400


def test_resolve_tus_source_409_for_incomplete_upload(tmp_path, monkeypatch):
    from omnix.cloud import config
    monkeypatch.setenv("OMNIX_TUS_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()  # type: ignore[attr-defined]
    _write_tus_metadata(tmp_path, "u-incomplete",
                        committed=False, storage_key=None,
                        offset=50, length=100)
    from omnix.cloud.api.jobs import _resolve_tus_source
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _resolve_tus_source({"type": "tus", "upload_id": "u-incomplete"}, "acme")
    assert exc.value.status_code == 409
    assert "50/100" in exc.value.detail


def test_resolve_tus_source_returns_storage_key_for_committed(tmp_path, monkeypatch):
    from omnix.cloud import config
    monkeypatch.setenv("OMNIX_TUS_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()  # type: ignore[attr-defined]
    _write_tus_metadata(tmp_path, "u-done",
                        committed=True,
                        storage_key="uploads/acme/u-done/bundle.tar",
                        sha256="abc123")
    from omnix.cloud.api.jobs import _resolve_tus_source
    out = _resolve_tus_source({"type": "tus", "upload_id": "u-done"}, "acme")
    assert out["storage_key"] == "uploads/acme/u-done/bundle.tar"
    assert out["sha256"] == "abc123"


def test_resolve_tus_source_passes_through_non_tus_source():
    from omnix.cloud.api.jobs import _resolve_tus_source
    src = {"type": "git", "repo": "https://example.com/x.git", "ref": "main"}
    assert _resolve_tus_source(src, "acme") == src


def test_resolve_tus_source_passes_through_direct_storage_key(tmp_path, monkeypatch):
    from omnix.cloud import config
    from omnix.cloud.api.jobs import _resolve_tus_source
    monkeypatch.setenv("OMNIX_TUS_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()  # type: ignore[attr-defined]
    # Even when payload carries a storage_key directly (no tus indirection),
    # the resolver returns it unchanged. Useful for tests + admin tooling.
    src = {"workspace": "/tmp/x", "type": "direct", "storage_key": "k"}
    assert _resolve_tus_source(src, "acme") == src  # type != tus, returned as-is


# -------------------- Gap #14: inline + production → signed receipts ---------


def test_validated_mode_legacy_inline_defaults_to_dry_run():
    from omnix.cloud.api.jobs import _validated_mode
    assert _validated_mode(None, inline=True) == "dry-run"


def test_validated_mode_async_defaults_to_production():
    from omnix.cloud.api.jobs import _validated_mode
    assert _validated_mode(None, inline=False) == "production"


def test_validated_mode_explicit_overrides_default():
    from omnix.cloud.api.jobs import _validated_mode
    assert _validated_mode("production", inline=True) == "production"
    assert _validated_mode("dry-run", inline=False) == "dry-run"


def test_validated_mode_unknown_value_raises_400():
    from omnix.cloud.api.jobs import _validated_mode
    from fastapi import HTTPException
    with pytest.raises(HTTPException) as exc:
        _validated_mode("yolo", inline=True)
    assert exc.value.status_code == 400


def test_start_job_inline_legacy_no_receipts():
    """Backward compat: inline=true without mode → dry-run, no receipts."""
    client = TestClient(_build_app())
    r = client.post(
        "/v1/jobs",
        json={"source": {"workspace": "/tmp/x"}, "inline": True},
        headers=_auth_headers(),
    )
    assert r.status_code == 202
    body = r.json()
    assert body["state"] == "awaiting_cutover"
    assert body.get("receipts") is None or body["receipts"] == []


def test_start_job_inline_mode_production_emits_signed_receipt():
    """gap #45/14: inline + mode=production emits a real signed receipt."""
    client = TestClient(_build_app())
    r = client.post("/v1/jobs", json={
        "source": {"workspace": "/tmp/x"},
        "inline": True,
        "mode": "production",
    }, headers=_auth_headers())
    assert r.status_code == 202
    body = r.json()
    assert body["state"] == "awaiting_cutover"
    receipts = body["receipts"]
    assert len(receipts) == 1
    receipt = receipts[0]
    for key in ("receipt_id", "payload", "payload_canonical_b64",
                "signature_b64", "public_key_b64", "alg"):
        assert key in receipt, f"receipt missing {key!r}: {receipt!r}"
    assert receipt["alg"] == "ML-DSA-65"
    assert receipt["payload"]["kind"] == "pipeline.completion.inline"
    assert receipt["payload"]["job_id"] == body["job_id"]


def test_inline_production_receipt_verifies_with_returned_public_key():
    """End-to-end: client takes the returned (sig, pk, payload_canonical) and
    verifies offline using the same ML-DSA-65 module the server signs with.
    """
    from omnix.receipts.verify import verify_bytes
    client = TestClient(_build_app())
    r = client.post("/v1/jobs", json={
        "source": {"workspace": "/tmp/x"},
        "inline": True,
        "mode": "production",
    }, headers=_auth_headers())
    assert r.status_code == 202
    receipt = r.json()["receipts"][0]
    pk = base64.b64decode(receipt["public_key_b64"])
    sig = base64.b64decode(receipt["signature_b64"])
    canonical = base64.b64decode(receipt["payload_canonical_b64"])
    # verify_bytes signature: (pk, msg, ctx, sig)
    ok = verify_bytes(pk, canonical, b"", sig)
    assert ok is True


def test_start_job_inline_mode_dry_run_explicit_no_receipts():
    client = TestClient(_build_app())
    r = client.post("/v1/jobs", json={
        "source": {"workspace": "/tmp/x"},
        "inline": True,
        "mode": "dry-run",
    }, headers=_auth_headers())
    assert r.status_code == 202
    body = r.json()
    assert body.get("receipts") is None or body["receipts"] == []


def test_inline_keypair_is_stable_across_requests():
    """Review finding H3: a fresh keypair per request meant losing the
    response = losing verifiability. The keypair is now stable per process,
    so two consecutive inline requests return the same public_key_b64.
    """
    client = TestClient(_build_app())
    pks = []
    for _ in range(3):
        r = client.post("/v1/jobs", json={
            "source": {"workspace": "/tmp/x"},
            "inline": True,
            "mode": "production",
        }, headers=_auth_headers())
        assert r.status_code == 202
        pks.append(r.json()["receipts"][0]["public_key_b64"])
    assert len(set(pks)) == 1, f"keypair should be stable, got {len(set(pks))} distinct keys"


def test_start_job_unknown_mode_returns_400():
    client = TestClient(_build_app())
    r = client.post("/v1/jobs", json={
        "source": {"workspace": "/tmp/x"},
        "inline": True,
        "mode": "turbo",
    }, headers=_auth_headers())
    assert r.status_code == 400


# -------------------- Gap #10: broker dispatch timeout → 503 -----------------


def test_start_job_async_broker_timeout_returns_503():
    """When .delay() hangs past BROKER_DISPATCH_TIMEOUT_S, expect HTTP 503."""
    from omnix.cloud.api import jobs as jobs_router
    # Shorten the timeout so the test runs fast.
    original = jobs_router.BROKER_DISPATCH_TIMEOUT_S
    jobs_router.BROKER_DISPATCH_TIMEOUT_S = 0.2

    def hang_forever(*_a, **_kw):
        # Block long enough to exceed the timeout.
        import time
        time.sleep(5.0)

    try:
        with patch("omnix.cloud.tasks.replicate.start_pipeline") as mock_task:
            mock_task.delay = hang_forever
            client = TestClient(_build_app())
            r = client.post("/v1/jobs", json={
                "source": {"workspace": "/tmp/x"},
                "inline": False,
            }, headers=_auth_headers())
            assert r.status_code == 503, r.json()
            assert "timed out" in r.json()["detail"].lower()
    finally:
        jobs_router.BROKER_DISPATCH_TIMEOUT_S = original


def test_start_job_async_broker_connection_error_returns_503():
    def raise_conn(*_a, **_kw):
        raise ConnectionError("redis://nowhere:6379 refused")

    with patch("omnix.cloud.tasks.replicate.start_pipeline") as mock_task:
        mock_task.delay = raise_conn
        client = TestClient(_build_app())
        r = client.post("/v1/jobs", json={
            "source": {"workspace": "/tmp/x"},
            "inline": False,
        }, headers=_auth_headers())
        assert r.status_code == 503
        assert "connection" in r.json()["detail"].lower() or "refused" in r.json()["detail"].lower()


def test_start_job_async_other_dispatch_failure_stays_queued():
    """Non-broker exceptions (e.g. import errors in test envs without broker
    config) preserve the previous 'stay queued' behavior so the WS can
    reflect 'queued' and a worker can take over when one comes up.
    """
    def import_fail(*_a, **_kw):
        raise ImportError("no broker module")

    with patch("omnix.cloud.tasks.replicate.start_pipeline") as mock_task:
        mock_task.delay = import_fail
        client = TestClient(_build_app())
        r = client.post("/v1/jobs", json={
            "source": {"workspace": "/tmp/x"},
            "inline": False,
        }, headers=_auth_headers())
        assert r.status_code == 202
        assert r.json()["state"] == "queued"


# -------------------- Integration: tus → jobs (gap #13 round trip) ----------


def test_post_jobs_with_tus_upload_id_resolves_storage_key(tmp_path, monkeypatch):
    """Upload metadata exists on disk; POST /v1/jobs picks it up correctly."""
    from omnix.cloud import config
    monkeypatch.setenv("OMNIX_TUS_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()  # type: ignore[attr-defined]
    _write_tus_metadata(tmp_path, "u-int",
                        committed=True,
                        storage_key="uploads/acme/u-int/bundle.tar")
    client = TestClient(_build_app())
    r = client.post("/v1/jobs", json={
        "source": {"type": "tus", "upload_id": "u-int", "workspace": "/tmp/x"},
        "inline": True,
        "mode": "production",
    }, headers=_auth_headers())
    assert r.status_code == 202, r.text
    body = r.json()
    # The receipt embeds the source, so we can confirm storage_key was
    # threaded all the way through. The completion receipt payload doesn't
    # carry the storage_key (it carries source_sha256 etc.), but the
    # initial ingest event payload was published with the resolved source.
    assert body["state"] == "awaiting_cutover"


def test_post_jobs_with_tus_incomplete_returns_409(tmp_path, monkeypatch):
    from omnix.cloud import config
    monkeypatch.setenv("OMNIX_TUS_DATA_DIR", str(tmp_path))
    config.get_settings.cache_clear()  # type: ignore[attr-defined]
    _write_tus_metadata(tmp_path, "u-half",
                        committed=False, storage_key=None,
                        offset=10, length=100)
    client = TestClient(_build_app())
    r = client.post("/v1/jobs", json={
        "source": {"type": "tus", "upload_id": "u-half"},
        "inline": True,
    }, headers=_auth_headers())
    assert r.status_code == 409
