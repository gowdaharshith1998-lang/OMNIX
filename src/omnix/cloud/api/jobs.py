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

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Header, HTTPException, Query
from pydantic import BaseModel, Field

from omnix.cloud import events

router = APIRouter()


class StartJobRequest(BaseModel):
    source: dict = Field(..., description="Either {type: tus, upload_id} or {type: git, repo, ref}")
    target_language: str = Field("java21", min_length=2, max_length=32)
    project_slug: str | None = None
    inline: bool = Field(False, description="run synchronously inside the request (tests only)")


class StartJobResponse(BaseModel):
    job_id: str
    ws_url: str
    state: str


@router.post("", response_model=StartJobResponse, status_code=202)
async def start_job(
    payload: Annotated[StartJobRequest, Body(...)],
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    job_id = uuid.uuid4().hex
    events.publish(job_id, "ingest", "job created",
                   payload={"source": payload.source, "target": payload.target_language})

    if payload.inline:
        from omnix.cloud.pipeline.runner import run_pipeline

        source = payload.source
        run_pipeline(
            job_id=job_id,
            workspace=source.get("workspace"),
            artifact_storage_key=source.get("storage_key"),
            tenant_id=x_tenant_id,
            source_repo=source.get("repo"),
            source_sha=source.get("sha"),
            source_sha256=source.get("sha256"),
            target_language=payload.target_language,
            dry_run=True,
        )
        return StartJobResponse(
            job_id=job_id, ws_url=f"/ws/jobs/{job_id}", state="awaiting_cutover"
        )

    # Async path: dispatch to Celery. In environments without a worker, we
    # let the API stay live and let the WS reflect "queued" — the worker will
    # take over when one comes up.
    try:
        from omnix.cloud.tasks.replicate import start_pipeline

        source = payload.source
        start_pipeline.delay(
            job_id=job_id,
            workspace=source.get("workspace"),
            artifact_storage_key=source.get("storage_key"),
            tenant_id=x_tenant_id,
            source_repo=source.get("repo"),
            source_sha=source.get("sha"),
            source_sha256=source.get("sha256"),
            target_language=payload.target_language,
        )
    except Exception:  # noqa: BLE001 — Celery broker may not be up in tests
        events.publish(job_id, "ingest", "celery dispatch failed; staying queued",
                       severity="warn")

    return StartJobResponse(job_id=job_id, ws_url=f"/ws/jobs/{job_id}", state="queued")


@router.get("/{job_id}")
async def job_status(job_id: str):
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
async def list_events(job_id: str, since_seq: int = Query(0, ge=0)):
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
