"""POST /v1/cutover/{unit}/shift     request a traffic-shift
POST /v1/cutover/{unit}/rollback  emergency rollback (signed)
GET  /v1/cutover/{unit}            current state + history
GET  /v1/cutover/units             snapshot of every (tenant, unit) state
GET  /v1/cutover/events            SSE stream of every authorized shift
"""

from __future__ import annotations

import json
import logging
import os
from typing import Annotated

from fastapi import APIRouter, Body, Header, HTTPException, Request
from pydantic import BaseModel, Field
from sse_starlette.sse import EventSourceResponse

from omnix.cloud.cutover.event_bus import (
    InMemoryCutoverBus,
    RedisStreamsCutoverBus,
)
from omnix.cloud.cutover.facade_controller import (
    FacadeController,
    event_to_dict,
    real_signer,
)
from omnix.cloud.auth.tenancy import require_session_tenant

log = logging.getLogger("omnix.cloud.api.cutover")


def _build_bus():
    """Pick the bus implementation from the environment.

    - ``OMNIX_CUTOVER_BUS_URL=redis://...`` → ``RedisStreamsCutoverBus``
      (cross-pod, cross-worker delivery).
    - ``OMNIX_REDIS_URL=...`` is honored as a fallback so deployments that
      already expose a Redis URL get cross-worker delivery for free.
    - Otherwise ``InMemoryCutoverBus`` — single-process only.

    Why this matters: gunicorn defaults to multiple uvicorn workers per Pod.
    With the in-memory bus, a POST /shift on worker A and an SSE subscriber
    on worker B never see each other's events — the writer sidecar would
    hang silently. Surfaced by the verify dispatch Phase D.
    """
    url = os.environ.get("OMNIX_CUTOVER_BUS_URL") or os.environ.get("OMNIX_REDIS_URL")
    if url:
        try:
            log.info("cutover event bus: Redis Streams (%s)", url)
            return RedisStreamsCutoverBus(url)
        except Exception:  # noqa: BLE001
            log.exception("RedisStreamsCutoverBus init failed; falling back to InMemory")
    log.info("cutover event bus: in-memory (single-process only)")
    return InMemoryCutoverBus()


router = APIRouter()
_BUS = _build_bus()
_CONTROLLER = FacadeController(signer=real_signer(), event_bus=_BUS)


def get_controller() -> FacadeController:
    return _CONTROLLER


def get_bus():
    return _BUS


def set_controller(controller: FacadeController) -> None:
    """Test hook."""
    global _CONTROLLER
    _CONTROLLER = controller


def set_bus(bus) -> None:
    """Test hook."""
    global _BUS
    _BUS = bus


class ShiftRequest(BaseModel):
    target_percentage: int = Field(..., ge=0, le=100)
    verifier_summary: dict = Field(default_factory=dict)


@router.post("/{unit_id}/shift")
async def shift(
    unit_id: str,
    payload: Annotated[ShiftRequest, Body(...)],
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    tenant_id = require_session_tenant(x_tenant_id)
    event = get_controller().request_shift(
        tenant_id=tenant_id,
        unit_id=unit_id,
        target_percentage=payload.target_percentage,
        verifier_summary=payload.verifier_summary,
    )
    if event.rejected_reason:
        return event_to_dict(event) | {"status": "rejected"}
    return event_to_dict(event) | {"status": "authorized"}


@router.post("/{unit_id}/rollback")
async def rollback(
    unit_id: str,
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    tenant_id = require_session_tenant(x_tenant_id)
    event = get_controller().rollback(tenant_id=tenant_id, unit_id=unit_id)
    return event_to_dict(event) | {"status": "rolled_back"}


@router.get("/units")
async def list_units():
    """Bootstrap snapshot of every (tenant, unit) → percentage.

    Used by ``facade_writer_runner`` to seed routes.json before subscribing
    to live events. No auth: this is read-only state derived from the
    controller's in-memory routing table.
    """
    controller = get_controller()
    out = []
    with controller._lock:  # noqa: SLF001 — same-package introspection
        for (tenant_id, unit_id), state in controller._states.items():
            out.append({
                "tenant_id": tenant_id,
                "unit_id": unit_id,
                "percentage": state.percentage,
            })
    return {"units": out}


@router.get("/events")
async def stream_events(
    request: Request,
    last_event_id: str | None = Header(None, alias="Last-Event-ID"),
):
    """SSE stream of every authorized shift the controller emits.

    The facade_writer_runner sidecar consumes this. Each frame includes an
    ``id`` so reconnecting clients can resume via ``Last-Event-ID``. A
    keepalive event is sent every 15s so intermediaries don't drop the
    long-lived connection.
    """
    bus = get_bus()

    async def event_generator():
        async for event_id, payload in bus.subscribe(last_event_id):
            if await request.is_disconnected():
                break
            yield {
                "id": event_id,
                "event": "cutover-shift",
                "data": json.dumps(payload),
            }

    return EventSourceResponse(
        event_generator(),
        ping=15,
        ping_message_factory=lambda: {"event": "keepalive", "data": "{}"},
    )


@router.get("/{unit_id}")
async def get_state(
    unit_id: str,
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    tenant_id = require_session_tenant(x_tenant_id)
    state = get_controller().state(tenant_id, unit_id)
    return {
        "tenant_id": state.tenant_id,
        "unit_id": state.unit_id,
        "percentage": state.percentage,
        "history": [event_to_dict(e) for e in state.history],
    }
