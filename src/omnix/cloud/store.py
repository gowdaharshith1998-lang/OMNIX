"""Durable persistence for job state, events, receipts, and tenant tier.

Why this exists
---------------
The job-event bus (``omnix.cloud.events``) keeps a fast in-process fan-out for
live WebSocket streaming and for single-process dev/test. That alone is *not*
durable: state is lost on restart and is invisible across the API's gunicorn
workers and the Celery worker process. This module is the durable, cross-process
source of truth — every event is also written to Postgres, and reads can be
served from Postgres so any worker/pod sees the same job history.

Opt-in by design
----------------
Persistence is enabled only when ``OMNIX_EVENTS_PERSIST`` is truthy. With it
off (the default), the system behaves exactly as before — pure in-memory — so
local dev and the test-suite need no database. Production deployments set the
flag and point ``OMNIX_SYNC_DATABASE_URL`` at Postgres.

All writes are best-effort: a database hiccup degrades to the in-memory path
and is logged, rather than failing the request. The synchronous engine is used
throughout so the same helpers work from the async API handlers (via
``asyncio.to_thread`` at the call site) and the sync Celery worker.
"""

from __future__ import annotations

import logging
import os
from typing import Any

from sqlalchemy import func, select

from omnix.cloud.db.models import Job, JobEvent, JobState, Receipt, Tenant, TenantTier
from omnix.cloud.db.session import sync_session_scope

log = logging.getLogger("omnix.cloud.store")

# gate name -> job lifecycle state
_GATE_TO_STATE: dict[str, JobState] = {
    "ingest": JobState.INGESTING,
    "parse": JobState.PARSING,
    "spec": JobState.SPEC_MINING,
    "generate": JobState.GENERATING,
    "verify": JobState.VERIFYING,
    "cutover": JobState.AWAITING_CUTOVER,
    "complete": JobState.COMPLETE,
    "error": JobState.FAILED,
}


def persistence_enabled() -> bool:
    """True when durable persistence is switched on for this process."""
    return os.environ.get("OMNIX_EVENTS_PERSIST", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def record_job(
    job_id: str,
    *,
    tenant_id: str,
    mode: str,
    state: str = "queued",
) -> None:
    """Insert the parent Job row so later events have something to reference.

    Idempotent: a second call for the same job_id is a no-op. The ``mode`` is
    the ingestion mode (tus_upload / git_clone / live_observe); unknown values
    fall back to ``tus_upload`` so a malformed request cannot wedge the row.
    """
    if not persistence_enabled():
        return
    try:
        from omnix.cloud.db.models import IngestionMode

        try:
            ingestion = IngestionMode(mode)
        except ValueError:
            ingestion = IngestionMode.TUS_UPLOAD
        try:
            job_state = JobState(state)
        except ValueError:
            job_state = JobState.QUEUED
        with sync_session_scope() as s:
            existing = s.get(Job, job_id)
            if existing is not None:
                return
            s.add(
                Job(
                    id=job_id,
                    tenant_id=tenant_id,
                    mode=ingestion,
                    state=job_state,
                )
            )
    except Exception:  # noqa: BLE001 - durability is best-effort
        log.warning("record_job failed for %s", job_id, exc_info=True)


def next_seq_and_persist(
    *,
    job_id: str,
    gate: str | None,
    severity: str,
    message: str,
    payload: dict[str, Any],
    ts: str,
) -> int | None:
    """Atomically allocate the next per-job seq and persist the event row.

    Returns the allocated seq, or ``None`` if persistence is off or failed (the
    caller then falls back to the in-memory sequence).
    """
    if not persistence_enabled():
        return None
    try:
        with sync_session_scope() as s:
            current_max = s.execute(
                select(func.coalesce(func.max(JobEvent.seq), 0)).where(
                    JobEvent.job_id == job_id
                )
            ).scalar_one()
            seq = int(current_max) + 1
            s.add(
                JobEvent(
                    job_id=job_id,
                    seq=seq,
                    gate=gate,
                    severity=severity,
                    message=message,
                    payload=payload or {},
                )
            )
            # Advance parent job state if the row exists and the gate maps.
            job = s.get(Job, job_id)
            if job is not None and gate in _GATE_TO_STATE:
                job.state = _GATE_TO_STATE[gate]
            return seq
    except Exception:  # noqa: BLE001
        log.warning("persist event failed for %s", job_id, exc_info=True)
        return None


def load_events(job_id: str) -> list[dict[str, Any]] | None:
    """Return the durable event log for a job, or ``None`` if persistence off."""
    if not persistence_enabled():
        return None
    try:
        with sync_session_scope() as s:
            rows = s.execute(
                select(JobEvent).where(JobEvent.job_id == job_id).order_by(JobEvent.seq)
            ).scalars().all()
            return [
                {
                    "job_id": r.job_id,
                    "seq": r.seq,
                    "gate": r.gate,
                    "severity": r.severity,
                    "message": r.message,
                    "payload": r.payload or {},
                    "ts": r.created_at.isoformat() if r.created_at else None,
                }
                for r in rows
            ]
    except Exception:  # noqa: BLE001
        log.warning("load_events failed for %s", job_id, exc_info=True)
        return None


def get_job_tenant(job_id: str) -> str | None:
    """Return the owning tenant_id for a job, or None if unknown/persist-off."""
    if not persistence_enabled():
        return None
    try:
        with sync_session_scope() as s:
            job = s.get(Job, job_id)
            return job.tenant_id if job is not None else None
    except Exception:  # noqa: BLE001
        log.warning("get_job_tenant failed for %s", job_id, exc_info=True)
        return None


def persist_receipt(
    *,
    job_id: str,
    tenant_id: str,
    receipt_kind: str,
    payload_canonical: bytes,
    payload_json: dict[str, Any],
    payload_sha256: str,
    signature: bytes,
    public_key: bytes,
) -> None:
    """Append a signed receipt row (best-effort)."""
    if not persistence_enabled():
        return
    try:
        with sync_session_scope() as s:
            s.add(
                Receipt(
                    job_id=job_id,
                    tenant_id=tenant_id,
                    receipt_kind=receipt_kind,
                    payload_canonical=payload_canonical,
                    payload_json=payload_json,
                    payload_sha256=payload_sha256,
                    signature=signature,
                    public_key=public_key,
                )
            )
    except Exception:  # noqa: BLE001
        log.warning("persist_receipt failed for %s", job_id, exc_info=True)


def set_tenant_tier(tenant_id: str, tier: str) -> bool:
    """Persist a tenant's subscription tier. Returns True if a row was updated.

    Used by the Stripe webhook so paid upgrades/downgrades actually take
    effect instead of being computed and thrown away.
    """
    if not persistence_enabled():
        return False
    try:
        tier_enum = TenantTier(tier)
    except ValueError:
        log.warning("set_tenant_tier: unknown tier %r", tier)
        return False
    try:
        with sync_session_scope() as s:
            tenant = s.get(Tenant, tenant_id)
            if tenant is None:
                return False
            tenant.tier = tier_enum
            return True
    except Exception:  # noqa: BLE001
        log.warning("set_tenant_tier failed for %s", tenant_id, exc_info=True)
        return False
