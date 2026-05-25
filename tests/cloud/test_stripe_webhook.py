"""Stripe webhook tests."""

from __future__ import annotations

import hashlib
import hmac
import json
import time

import pytest

from omnix.cloud.api.stripe_webhook import (
    resolve_tier_from_event,
    verify_stripe_signature,
)


def _sign(secret: str, payload: bytes, *, t: int | None = None) -> tuple[str, int]:
    t = t or int(time.time())
    sig = hmac.new(secret.encode(), f"{t}.".encode() + payload, hashlib.sha256).hexdigest()
    return f"t={t},v1={sig}", t


def test_verify_signature_accepts_fresh_signed_payload():
    secret = "whsec_test"
    payload = b'{"id":"evt_1"}'
    header, _ = _sign(secret, payload)
    assert verify_stripe_signature(payload, header, secret)


def test_verify_signature_rejects_expired_timestamp():
    secret = "whsec_test"
    payload = b'{"id":"evt_1"}'
    header, _ = _sign(secret, payload, t=int(time.time()) - 1000)
    assert not verify_stripe_signature(payload, header, secret, tolerance=300)


def test_verify_signature_rejects_wrong_secret():
    payload = b'{"id":"evt_1"}'
    header, _ = _sign("wrong_secret", payload)
    assert not verify_stripe_signature(payload, header, "correct_secret")


def test_verify_signature_rejects_malformed_header():
    assert not verify_stripe_signature(b"{}", "garbage", "whsec")


def test_resolve_tier_team_subscription():
    event = {
        "type": "customer.subscription.created",
        "data": {"object": {
            "metadata": {"omnix_tenant_id": "t-1"},
            "items": {"data": [{"price": {"id": "price_team_monthly_99"}}]},
        }},
    }
    tenant_id, tier = resolve_tier_from_event(event)
    assert tenant_id == "t-1"
    assert tier == "team"


def test_resolve_tier_enterprise():
    event = {
        "type": "customer.subscription.updated",
        "data": {"object": {
            "metadata": {"omnix_tenant_id": "t-bank"},
            "items": {"data": [{"price": {"id": "price_ent_annual"}}]},
        }},
    }
    tenant_id, tier = resolve_tier_from_event(event)
    assert tier == "banking"


def test_resolve_tier_ignores_unrelated_event():
    event = {"type": "invoice.payment_succeeded", "data": {"object": {}}}
    tenant_id, tier = resolve_tier_from_event(event)
    assert tenant_id is None and tier is None
