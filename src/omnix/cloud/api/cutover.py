"""POST /v1/cutover/{unit}/shift     request a traffic-shift
POST /v1/cutover/{unit}/rollback  emergency rollback (signed)
GET  /v1/cutover/{unit}            current state + history
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Body, Header, HTTPException
from pydantic import BaseModel, Field

from omnix.cloud.cutover.facade_controller import (
    FacadeController,
    event_to_dict,
    real_signer,
)

router = APIRouter()
_CONTROLLER = FacadeController(signer=real_signer())


def get_controller() -> FacadeController:
    return _CONTROLLER


def set_controller(controller: FacadeController) -> None:
    """Test hook."""
    global _CONTROLLER
    _CONTROLLER = controller


class ShiftRequest(BaseModel):
    target_percentage: int = Field(..., ge=0, le=100)
    verifier_summary: dict = Field(default_factory=dict)


@router.post("/{unit_id}/shift")
async def shift(
    unit_id: str,
    payload: Annotated[ShiftRequest, Body(...)],
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-Id required")
    event = get_controller().request_shift(
        tenant_id=x_tenant_id,
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
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-Id required")
    event = get_controller().rollback(tenant_id=x_tenant_id, unit_id=unit_id)
    return event_to_dict(event) | {"status": "rolled_back"}


@router.get("/{unit_id}")
async def get_state(
    unit_id: str,
    x_tenant_id: str | None = Header(None, alias="X-Tenant-Id"),
):
    if not x_tenant_id:
        raise HTTPException(status_code=400, detail="X-Tenant-Id required")
    state = get_controller().state(x_tenant_id, unit_id)
    return {
        "tenant_id": state.tenant_id,
        "unit_id": state.unit_id,
        "percentage": state.percentage,
        "history": [event_to_dict(e) for e in state.history],
    }
