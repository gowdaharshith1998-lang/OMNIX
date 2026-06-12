"""Stripe webhook receiver.

Verifies Stripe-Signature, then routes subscription events to update the
Tenant.tier and quota allocations. We do NOT take a hard dependency on the
``stripe`` Python SDK because verification is straightforward HMAC-SHA256.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import time
from typing import Annotated

from fastapi import APIRouter, Header, HTTPException, Request

router = APIRouter()


def verify_stripe_signature(payload: bytes, sig_header: str, secret: str,
                            *, tolerance: int = 300) -> bool:
    """Verify Stripe webhook signature per Stripe's published algorithm."""
    timestamp = None
    signatures: list[str] = []
    for item in sig_header.split(","):
        kv = item.strip().split("=", 1)
        if len(kv) != 2:
            continue
        if kv[0] == "t":
            try:
                timestamp = int(kv[1])
            except ValueError:
                return False
        elif kv[0] == "v1":
            signatures.append(kv[1])
    if timestamp is None or not signatures:
        return False
    if abs(int(time.time()) - timestamp) > tolerance:
        return False

    signed_payload = f"{timestamp}.".encode() + payload
    expected = hmac.new(secret.encode(), signed_payload, hashlib.sha256).hexdigest()
    return any(hmac.compare_digest(expected, s) for s in signatures)


# Stripe event → tier policy
_TIER_BY_PRICE_PREFIX: dict[str, str] = {
    "price_free":  "smb",
    "price_team":  "team",
    "price_ent":   "banking",
}


def resolve_tier_from_event(event: dict) -> tuple[str | None, str | None]:
    """(tenant_id, tier) tuple, or (None, None) if not applicable."""
    if event.get("type") not in {
        "customer.subscription.created",
        "customer.subscription.updated",
        "customer.subscription.deleted",
    }:
        return None, None
    sub = event.get("data", {}).get("object", {})
    metadata = sub.get("metadata", {})
    tenant_id = metadata.get("omnix_tenant_id")
    if not tenant_id:
        return None, None
    items = sub.get("items", {}).get("data", [])
    if not items:
        return tenant_id, "smb"
    price_id = items[0].get("price", {}).get("id", "")
    for prefix, tier in _TIER_BY_PRICE_PREFIX.items():
        if price_id.startswith(prefix):
            return tenant_id, tier
    return tenant_id, "smb"


@router.post("/stripe-webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Annotated[str | None, Header(alias="Stripe-Signature")] = None,
):
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    if not secret:
        raise HTTPException(status_code=503, detail="stripe webhook not configured")
    payload = await request.body()
    if not stripe_signature or not verify_stripe_signature(payload, stripe_signature, secret):
        raise HTTPException(status_code=400, detail="invalid stripe signature")
    import json
    event = json.loads(payload)
    tenant_id, tier = resolve_tier_from_event(event)

    # Actually persist the resolved tier — previously this endpoint computed
    # the new tier and discarded it, so paid upgrades/downgrades never took
    # effect. Best-effort: persistence is a no-op when OMNIX_EVENTS_PERSIST is
    # off (dev/test), and a missing tenant returns persisted=False rather than
    # erroring the webhook (Stripe would otherwise retry indefinitely).
    persisted = False
    if tenant_id and tier:
        import asyncio

        from omnix.cloud import store

        persisted = await asyncio.to_thread(store.set_tenant_tier, tenant_id, tier)

    return {
        "ok": True,
        "tenant_id": tenant_id,
        "tier": tier,
        "persisted": persisted,
        "event_type": event.get("type"),
    }
