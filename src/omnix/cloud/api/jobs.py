"""REST surface for replication jobs.

Endpoints:
  POST   /v1/jobs                          start (returns job_id, ws_url, receipt_urls)
  GET    /v1/jobs/{id}                     state + gate progress + receipt manifest
  GET    /v1/jobs/{id}/events              event log (paginated)
  GET    /v1/jobs/{id}/receipts            list receipts for the job
  GET    /v1/jobs/{id}/receipts/{rid}      download a single receipt (json+sig)
  GET    /v1/jobs/{id}/receipts/{rid}/verify  public verify (no auth)
"""

from __future__ import annotations

import asyncio
import uuid
from typing import Annotated, Any

from fastapi import APIRouter, Body, Header, HTTPException, Query
from pydantic import BaseModel, Field

from omnix.cloud import events
from omnix.cloud.auth.tenancy import require_session_tenant

router = APIRouter()

# Broker dispatch timeout. The previous behavior hung indefinitely when the
# Celery broker (Redis) was unreachable — gunicorn's worker timeout would
# eventually send SIGABRT to the worker, killing the request with no client
# response. 10s gives the broker enough time on a healthy network and
# converts unreachability into a clean 503.
BROKER_DISPATCH_TIMEOUT_S = 10.0


class StartJobRequest(BaseModel):
    source: dict = Field(..., description="Either {type: tus, upload_id} or {type: git, repo, ref}")
    target_language: str = Field("java21", min_length=2, max_length=32)
    project_slug: str | None = None
    inline: bool = Field(False, description="run synchronously inside the request (tests only)")
    mode: str | None = Field(
        None,
        description=(
            "Authoritative pipeline mode: 'dry-run' (no receipts) | 'production' "
            "(signed receipts). When omitted with inline=true, defaults to "
            "'dry-run' for backward compatibility; when omitted with inline=false, "
            "the async worker runs in full production mode."
        ),
    )


class StartJobResponse(BaseModel):
    job_id: str
    ws_url: str
    state: str
    receipts: list[dict] | None = None


def _resolve_tus_source(source: dict[str, Any], tenant_id: str) -> dict[str, Any]:
    """If source carries an upload_id, resolve it to a storage_key + sha256.

    Returns a new dict with storage_key / sha256 populated. Raises HTTP
    errors for missing or incomplete uploads — the alternative (silently
    leaving storage_key=None and letting the runner crash later) was the
    exact gap #45/13 surfaced by verify dispatch.
    """
    from omnix.cloud.ingest.tus_handler import get_upload_metadata

    if source.get("type") != "tus":
        return source
    upload_id = source.get("upload_id")
    if not upload_id:
        raise HTTPException(status_code=400, detail="source.upload_id required when type=tus")
    desc = get_upload_metadata(upload_id)
    if desc is None:
        raise HTTPException(status_code=404, detail=f"upload not found: {upload_id}")
    if desc.tenant_id != tenant_id:
        raise HTTPException(status_code=403, detail="upload belongs to another tenant")
    if not desc.committed:
        raise HTTPException(
            status_code=409,
            detail=(
                f"upload not yet complete: bytes_received={desc.offset}/"
                f"{desc.length}; finish the tus PATCH before POST /v1/jobs"
            ),
        )
    if not desc.storage_key:
        raise HTTPException(
            status_code=500,
            detail=f"upload {upload_id} is committed but has no storage_key",
        )
    resolved = dict(source)
    resolved["storage_key"] = desc.storage_key
    if desc.sha256 and "sha256" not in resolved:
        resolved["sha256"] = desc.sha256
    return resolved


def _validated_mode(mode: str | None, inline: bool) -> str:
    """Resolve the effective pipeline mode.

    - mode=None + inline=True  → "dry-run"   (backward-compat)
    - mode=None + inline=False → "production" (async path; current default)
    - mode set                 → validated and returned as-is
    """
    if mode is None:
        return "dry-run" if inline else "production"
    if mode not in ("dry-run", "production"):
        raise HTTPException(status_code=400, detail=f"unknown mode: {mode!r}")
    return mode


@router.post("", response_model=StartJobResponse, status_code=202)
async def start_job(
    payload: Annotated[StartJobRequest, Body(...)],
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    job_id = uuid.uuid4().hex
    tenant_id = require_session_tenant(x_tenant_id)
    source = _resolve_tus_source(payload.source, tenant_id)
    mode = _validated_mode(payload.mode, payload.inline)

    # Create the durable Job row (no-op unless persistence is enabled) BEFORE
    # the first event so the event rows have a parent to reference and reads
    # can authorize by tenant.
    from omnix.cloud import store

    ingestion_mode = "git_clone" if source.get("type") == "git" else "tus_upload"
    await asyncio.to_thread(
        store.record_job, job_id, tenant_id=tenant_id, mode=ingestion_mode
    )

    events.publish(job_id, "ingest", "job created",
                   payload={"source": source, "target": payload.target_language,
                            "mode": mode, "inline": payload.inline})

    if payload.inline:
        from omnix.cloud.pipeline.runner import run_pipeline

        result = run_pipeline(
            job_id=job_id,
            workspace=source.get("workspace"),
            artifact_storage_key=source.get("storage_key"),
            tenant_id=tenant_id,
            source_repo=source.get("repo"),
            source_sha=source.get("sha"),
            source_sha256=source.get("sha256"),
            target_language=payload.target_language,
            dry_run=(mode == "dry-run"),
            inline_production=(mode == "production"),
        )
        return StartJobResponse(
            job_id=job_id,
            ws_url=f"/ws/jobs/{job_id}",
            state="awaiting_cutover",
            receipts=result.get("receipts") or None,
        )

    # Async path: dispatch to Celery with a bounded timeout. Broker
    # unreachability now returns a 503 the client can handle instead of
    # hanging until gunicorn's worker timeout SIGABRTs the request.
    from omnix.cloud.tasks.replicate import start_pipeline

    async def _dispatch() -> None:
        await asyncio.to_thread(
            start_pipeline.delay,
            job_id=job_id,
            workspace=source.get("workspace"),
            artifact_storage_key=source.get("storage_key"),
            tenant_id=tenant_id,
            source_repo=source.get("repo"),
            source_sha=source.get("sha"),
            source_sha256=source.get("sha256"),
            target_language=payload.target_language,
        )

    try:
        await asyncio.wait_for(_dispatch(), timeout=BROKER_DISPATCH_TIMEOUT_S)
    except asyncio.TimeoutError as exc:
        events.publish(job_id, "ingest", "celery broker dispatch timed out",
                       severity="error", payload={"timeout_s": BROKER_DISPATCH_TIMEOUT_S})
        raise HTTPException(
            status_code=503,
            detail=(
                f"broker unreachable: dispatch timed out after "
                f"{BROKER_DISPATCH_TIMEOUT_S}s. Check OMNIX_REDIS_URL."
            ),
        ) from exc
    except (ConnectionError, OSError) as exc:
        events.publish(job_id, "ingest", f"celery broker connection error: {exc}",
                       severity="error")
        raise HTTPException(
            status_code=503,
            detail=f"broker connection error: {type(exc).__name__}: {exc}",
        ) from exc
    except Exception as exc:  # noqa: BLE001
        # Other exceptions are not necessarily broker problems (e.g. tests
        # without a configured broker raise ImportError on the inner
        # decorator). Preserve the previous "stay queued" semantics so the
        # WS reflects "queued" and a worker can pick up later if one comes
        # up — but record the cause for operators.
        events.publish(job_id, "ingest",
                       f"celery dispatch failed; staying queued: {type(exc).__name__}",
                       severity="warn")

    return StartJobResponse(job_id=job_id, ws_url=f"/ws/jobs/{job_id}", state="queued")


async def _authorize_job_read(job_id: str, x_tenant_id: str | None) -> None:
    """When persistence is on, a job's events may only be read by its owning
    tenant. With persistence off (single-process dev/test) there is no durable
    owner to check, so reads stay open as before."""
    from omnix.cloud import store

    owner = await asyncio.to_thread(store.get_job_tenant, job_id)
    if owner is None:
        return  # persistence off, or job not durably recorded
    tenant_id = require_session_tenant(x_tenant_id)
    if tenant_id != owner:
        # Do not leak existence to other tenants.
        raise HTTPException(status_code=404, detail="job not found")


@router.get("/{job_id}")
async def job_status(
    job_id: str,
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    await _authorize_job_read(job_id, x_tenant_id)
    hist = events.history(job_id)
    if not hist:
        raise HTTPException(status_code=404, detail="job not found")
    return {
        "job_id": job_id,
        "events": [
            {
                "seq": ev.seq,
                "gate": ev.gate,
                "severity": ev.severity,
                "message": ev.message,
                "ts": ev.ts,
            }
            for ev in hist
        ],
        "current_gate": hist[-1].gate,
        "state_hint": "complete" if hist[-1].gate == "complete" else "in_progress",
    }


@router.get("/{job_id}/events")
async def list_events(
    job_id: str,
    since_seq: int = Query(0, ge=0),
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    await _authorize_job_read(job_id, x_tenant_id)
    hist = events.history(job_id)
    return [
        {
            "seq": ev.seq,
            "gate": ev.gate,
            "severity": ev.severity,
            "message": ev.message,
            "payload": ev.payload,
            "ts": ev.ts,
        }
        for ev in hist
        if ev.seq > since_seq
    ]
