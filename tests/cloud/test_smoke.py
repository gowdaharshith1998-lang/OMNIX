"""Phase A0 smoke tests.

Verifies the cloud package imports, FastAPI responds, Celery app constructs.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_cloud_package_imports():
    import omnix.cloud  # noqa: F401
    import omnix.cloud.api.main as api_main  # noqa: F401
    import omnix.cloud.config as cfg  # noqa: F401
    import omnix.cloud.db.models as models  # noqa: F401
    import omnix.cloud.db.session as session  # noqa: F401
    import omnix.cloud.tasks.celery_app as celery_app  # noqa: F401


def test_settings_load_from_env():
    from omnix.cloud.config import get_settings

    settings = get_settings()
    assert settings.env == "dev"
    assert "sqlite" in settings.database_url
    assert settings.storage_backend == "memory"


def test_health_endpoint_responds():
    from omnix.cloud.api.main import create_app

    app = create_app()
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert "ts" in body


def test_version_endpoint_responds():
    from omnix.cloud.api.main import create_app

    client = TestClient(create_app())
    resp = client.get("/version")
    assert resp.status_code == 200
    body = resp.json()
    assert "omnix" in body
    assert "env" in body


def test_celery_app_constructed():
    from omnix.cloud.tasks.celery_app import celery_app, make_celery

    assert celery_app.conf.task_acks_late is True
    assert celery_app.conf.task_reject_on_worker_lost is True
    assert celery_app.conf.worker_prefetch_multiplier == 1
    # Idempotent factory.
    other = make_celery()
    assert other.main == celery_app.main


def test_models_metadata_has_expected_tables():
    from omnix.cloud.db.models import Base

    expected = {
        "tenants",
        "users",
        "projects",
        "jobs",
        "job_events",
        "receipts",
        "cutover_shifts",
    }
    actual = {t.name for t in Base.metadata.sorted_tables}
    missing = expected - actual
    assert not missing, f"missing tables: {missing}"


def test_receipts_table_has_no_updated_at_column():
    """Receipts are append-only (R1, R3). No mutator columns."""
    from omnix.cloud.db.models import Receipt

    cols = {c.name for c in Receipt.__table__.columns}
    assert "updated_at" not in cols
    assert "deleted_at" not in cols
