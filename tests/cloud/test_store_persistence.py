"""Durable cross-process persistence for the cloud job bus.

Exercises ``omnix.cloud.store`` + ``omnix.cloud.events`` against a real (file-
backed) SQLite database so the test proves the behaviour the in-memory bus
cannot: state survives a fresh in-process bus (stand-in for a different worker
process) and is read back from the database.
"""

from __future__ import annotations

import importlib

import pytest

from omnix.cloud.config import get_settings
from omnix.cloud.db import session as db_session
from omnix.cloud.db.models import Base, Receipt, Tenant


@pytest.fixture
def persistent_db(tmp_path, monkeypatch):
    """Point the sync engine at a temp SQLite file and enable persistence."""
    db_path = tmp_path / "omnix-test.db"
    monkeypatch.setenv("OMNIX_SYNC_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("OMNIX_EVENTS_PERSIST", "1")
    # Drop cached settings/engines so the new URL takes effect.
    get_settings.cache_clear()
    db_session.get_sync_engine.cache_clear()
    db_session.get_sync_session_maker.cache_clear()
    engine = db_session.get_sync_engine()
    Base.metadata.create_all(engine)
    yield engine
    get_settings.cache_clear()
    db_session.get_sync_engine.cache_clear()
    db_session.get_sync_session_maker.cache_clear()


def _seed_tenant(engine, tenant_id="t-acme", slug="acme") -> str:
    with engine.begin() as conn:
        from sqlalchemy import insert

        conn.execute(
            insert(Tenant).values(id=tenant_id, name="Acme", slug=slug)
        )
    return tenant_id


def test_events_persist_and_survive_new_bus(persistent_db):
    from omnix.cloud import events, store

    _seed_tenant(persistent_db)
    store.record_job("job-1", tenant_id="t-acme", mode="git_clone")

    events.publish("job-1", "ingest", "job created")
    events.publish("job-1", "parse", "parsing")
    events.publish("job-1", "complete", "done", severity="success")

    # Simulate a different process: blow away the in-memory bus entirely.
    events.reset_bus()

    hist = events.history("job-1")
    assert [e.gate for e in hist] == ["ingest", "parse", "complete"]
    assert [e.seq for e in hist] == [1, 2, 3]  # durable, monotonic seq
    assert hist[-1].message == "done"


def test_job_state_advances_with_gate(persistent_db):
    from omnix.cloud import events, store
    from omnix.cloud.db.models import Job, JobState

    _seed_tenant(persistent_db)
    store.record_job("job-2", tenant_id="t-acme", mode="tus_upload")
    events.publish("job-2", "verify", "verifying")

    with persistent_db.connect() as conn:
        from sqlalchemy.orm import Session

        with Session(bind=conn) as s:
            job = s.get(Job, "job-2")
            assert job is not None
            assert job.state == JobState.VERIFYING


def test_get_job_tenant_round_trips(persistent_db):
    from omnix.cloud import store

    _seed_tenant(persistent_db)
    store.record_job("job-3", tenant_id="t-acme", mode="git_clone")
    assert store.get_job_tenant("job-3") == "t-acme"
    assert store.get_job_tenant("nonexistent") is None


def test_set_tenant_tier_persists(persistent_db):
    from omnix.cloud import store
    from omnix.cloud.db.models import Tenant, TenantTier
    from sqlalchemy.orm import Session

    _seed_tenant(persistent_db)
    assert store.set_tenant_tier("t-acme", "banking") is True
    assert store.set_tenant_tier("missing-tenant", "team") is False

    with persistent_db.connect() as conn:
        with Session(bind=conn) as s:
            assert s.get(Tenant, "t-acme").tier == TenantTier.BANKING


def test_persist_receipt_appends_row(persistent_db):
    from omnix.cloud import store
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    _seed_tenant(persistent_db)
    store.record_job("job-4", tenant_id="t-acme", mode="git_clone")
    store.persist_receipt(
        job_id="job-4",
        tenant_id="t-acme",
        receipt_kind="pipeline.completion",
        payload_canonical=b'{"x":1}',
        payload_json={"x": 1},
        payload_sha256="a" * 64,
        signature=b"sig",
        public_key=b"pk",
    )
    with persistent_db.connect() as conn:
        with Session(bind=conn) as s:
            rows = s.execute(select(Receipt).where(Receipt.job_id == "job-4")).scalars().all()
            assert len(rows) == 1
            assert rows[0].receipt_kind == "pipeline.completion"


def test_inline_production_run_persists_events_and_receipt(persistent_db):
    """End-to-end: the runner's inline production path persists a durable event
    log and a signed completion receipt that survive a fresh bus."""
    from omnix.cloud import events, store
    from omnix.cloud.pipeline.runner import run_pipeline
    from omnix.cloud.db.models import Receipt
    from sqlalchemy import select
    from sqlalchemy.orm import Session

    _seed_tenant(persistent_db)
    store.record_job("job-run", tenant_id="t-acme", mode="git_clone")
    result = run_pipeline(
        job_id="job-run",
        workspace="/tmp/does-not-need-to-exist",
        artifact_storage_key=None,
        tenant_id="t-acme",
        target_language="java21",
        inline_production=True,
    )
    assert result["state"] == "awaiting_cutover"

    events.reset_bus()  # stand-in for a different process
    hist = events.history("job-run")
    gates = [e.gate for e in hist]
    assert "complete" in gates  # durable log visible cross-process

    with persistent_db.connect() as conn:
        with Session(bind=conn) as s:
            receipts = s.execute(
                select(Receipt).where(Receipt.job_id == "job-run")
            ).scalars().all()
            assert len(receipts) == 1
            assert receipts[0].public_key  # verification key persisted


def test_persistence_off_is_pure_in_memory(monkeypatch):
    """With the flag off, store helpers are no-ops and events stay in-memory."""
    monkeypatch.delenv("OMNIX_EVENTS_PERSIST", raising=False)
    from omnix.cloud import events, store

    assert store.persistence_enabled() is False
    assert store.get_job_tenant("whatever") is None
    assert store.load_events("whatever") is None
    events.reset_bus()
    events.publish("mem-job", "ingest", "hi")
    hist = events.history("mem-job")
    assert len(hist) == 1 and hist[0].seq == 1
