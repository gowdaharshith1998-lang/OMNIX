"""Celery application factory.

Locked anti-patterns from the dispatch:
  * task_acks_late=True for at-least-once delivery
  * single Beat process (we run zero scheduled tasks today; flag for HA later)
  * task bodies must be idempotent — we never write to .omnix/receipts/ from
    a task without an upstream content hash, and never call result.get() from
    inside another task
"""

from __future__ import annotations

from celery import Celery

from omnix.cloud.config import get_settings


def make_celery() -> Celery:
    settings = get_settings()
    app = Celery(
        "omnix.cloud",
        broker=settings.redis_url,
        backend=settings.redis_url,
        include=[
            "omnix.cloud.tasks.replicate",
            "omnix.cloud.tasks.ingest_complete",
        ],
    )
    app.conf.update(
        task_acks_late=True,
        task_reject_on_worker_lost=True,
        worker_prefetch_multiplier=1,
        task_track_started=True,
        task_time_limit=60 * 60 * 6,
        task_soft_time_limit=60 * 60 * 5,
        broker_connection_retry_on_startup=True,
        result_extended=True,
        task_default_queue="omnix.default",
        task_default_priority=5,
    )
    return app


celery_app = make_celery()
