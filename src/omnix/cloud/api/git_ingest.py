"""POST /v1/git/clone — kick off a git-based ingestion job.

Returns a job_id; the actual clone runs in a Celery worker (omnix.cloud.tasks.ingest_complete).
For tests, callers can pass `inline=True` to perform the clone in-process and skip Celery.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Body, Header, HTTPException
from pydantic import BaseModel, Field

from omnix.cloud.ingest.git_clone import GitIngestionError, clone_repository

router = APIRouter()


class GitCloneRequest(BaseModel):
    repo: str = Field(..., min_length=8, description="HTTPS URL of the repo")
    token: str | None = None
    ref: str | None = None
    inline: bool = False


class GitCloneResponse(BaseModel):
    job_id: str
    repo: str
    sha: str | None
    size_bytes: int | None
    workspace: str | None


@router.post("/clone", response_model=GitCloneResponse)
async def git_clone(
    payload: Annotated[GitCloneRequest, Body(...)],
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    job_id = uuid.uuid4().hex
    if payload.inline:
        try:
            result = clone_repository(payload.repo, token=payload.token, ref=payload.ref)
        except GitIngestionError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        return GitCloneResponse(
            job_id=job_id,
            repo=result.repo,
            sha=result.sha,
            size_bytes=result.size_bytes,
            workspace=result.workspace,
        )

    # Async path: dispatch a Celery task. For Phase A1 smoke we still return
    # the job_id immediately; the worker writes back via JobEvent rows.
    try:
        from omnix.cloud.tasks.ingest_complete import start_git_ingest

        start_git_ingest.delay(
            job_id=job_id,
            repo_url=payload.repo,
            token=payload.token,
            ref=payload.ref,
            tenant_id=x_tenant_id,
        )
    except Exception as exc:  # noqa: BLE001 - keep API responsive if Celery is down
        raise HTTPException(
            status_code=503,
            detail=f"git ingest dispatch failed: {exc.__class__.__name__}",
        ) from exc
    return GitCloneResponse(
        job_id=job_id,
        repo=payload.repo,
        sha=None,
        size_bytes=None,
        workspace=None,
    )
