"""The M1-orchestrator-wrapping Celery task.

Design constraints from the dispatch:
  * DO NOT modify the M1 orchestrator. Wrap it as a subprocess for isolation.
  * Stream stdout/stderr as gate events into the JobEvent bus.
  * Persist signed receipts to the Receipt table on final gate.

This module owns the *task surface*. The actual subprocess-driven pipeline
runner lives in :mod:`omnix.cloud.pipeline.runner` so we can unit-test the
runner without spinning up a Celery worker.
"""

from __future__ import annotations

from typing import Any

from omnix.cloud.tasks.celery_app import celery_app


@celery_app.task(name="omnix.cloud.replicate.start_pipeline", bind=True, max_retries=2)
def start_pipeline(
    self,
    job_id: str,
    workspace: str | None = None,
    artifact_storage_key: str | None = None,
    tenant_id: str | None = None,
    source_repo: str | None = None,
    source_sha: str | None = None,
    source_sha256: str | None = None,
    target_language: str = "java21",
    **extra: Any,
) -> dict[str, Any]:
    from omnix.cloud import events, store
    from omnix.cloud.pipeline.runner import run_pipeline

    # Idempotency guard: a retry or duplicate dispatch must not re-run a
    # pipeline that already finished (the pipeline itself is not idempotent —
    # it re-ingests and re-emits receipts). No-op unless durable persistence
    # is enabled, so dev/test behavior is unchanged.
    if store.job_already_finished(job_id):
        events.publish(
            job_id, "complete",
            "pipeline already finished; skipping duplicate run",
            severity="info",
        )
        return {"job_id": job_id, "state": "complete", "skipped": True, "receipts": []}

    try:
        return run_pipeline(
            job_id=job_id,
            workspace=workspace,
            artifact_storage_key=artifact_storage_key,
            tenant_id=tenant_id,
            source_repo=source_repo,
            source_sha=source_sha,
            source_sha256=source_sha256,
            target_language=target_language,
        )
    except Exception as exc:  # noqa: BLE001
        raise self.retry(exc=exc, countdown=60) from exc
