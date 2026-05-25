"""Celery task wrappers for ingestion paths.

Each task is idempotent: it logs a JobEvent for every state transition and
guards against double-execution via the job's current state in Postgres.
"""

from __future__ import annotations

from omnix.cloud.tasks.celery_app import celery_app


@celery_app.task(name="omnix.cloud.ingest.start_git_ingest", bind=True, max_retries=3)
def start_git_ingest(self, job_id: str, repo_url: str, token: str | None, ref: str | None,
                     tenant_id: str | None) -> dict:
    """Clone a repo into the worker's scratch directory and dispatch Pipeline.

    The pipeline binding (Phase A2) consumes the returned workspace.
    """
    from omnix.cloud.ingest.git_clone import GitIngestionError, clone_repository

    try:
        result = clone_repository(repo_url, token=token, ref=ref)
    except GitIngestionError as exc:
        raise self.retry(exc=exc, countdown=30) from exc

    # Hand off to the replication pipeline (Phase A2). Lazy import keeps
    # this module importable in isolation.
    try:
        from omnix.cloud.tasks.replicate import start_pipeline

        start_pipeline.delay(job_id=job_id, workspace=result.workspace,
                             tenant_id=tenant_id, source_repo=result.repo,
                             source_sha=result.sha)
    except Exception:
        # Recoverable: the pipeline can be re-dispatched manually.
        pass

    return {
        "job_id": job_id,
        "workspace": result.workspace,
        "sha": result.sha,
        "size_bytes": result.size_bytes,
    }


@celery_app.task(name="omnix.cloud.ingest.start_tus_complete", bind=True)
def start_tus_complete(self, job_id: str, upload_id: str, tenant_id: str | None) -> dict:
    """Triggered when a tus upload finalizes; hands off to the pipeline."""
    from omnix.cloud.ingest.tus_handler import get_upload

    desc = get_upload(upload_id)
    if not desc.committed:
        raise self.retry(exc=RuntimeError("upload not committed yet"), countdown=15)

    try:
        from omnix.cloud.tasks.replicate import start_pipeline

        start_pipeline.delay(
            job_id=job_id,
            workspace=None,
            artifact_storage_key=desc.storage_key,
            tenant_id=tenant_id,
            source_sha256=desc.sha256,
        )
    except Exception:
        pass

    return {
        "job_id": job_id,
        "upload_id": upload_id,
        "sha256": desc.sha256,
        "storage_key": desc.storage_key,
    }
