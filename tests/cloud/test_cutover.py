"""Cutover orchestration tests."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from omnix.cloud.api.main import create_app
from omnix.cloud.auth.jwt_session import issue
from omnix.cloud.cutover.facade_controller import (
    FacadeController,
    real_signer,
)


@pytest.fixture
def controller():
    return FacadeController(signer=real_signer())


def test_cutover_signer_key_is_anchored_not_ephemeral(tmp_path, monkeypatch):
    """The cutover signer must use a PERSISTENT key (anchored across instances
    and reloads), not a fresh ephemeral keypair per call."""
    import omnix.cloud.cutover.facade_controller as fc

    monkeypatch.setenv("OMNIX_CUTOVER_KEY_DIR", str(tmp_path / "ckey"))
    monkeypatch.setattr(fc, "_CUTOVER_KEYPAIR", None)

    msg = b"cutover-authorization"
    sig1, pk1 = real_signer()(msg)
    sig2, pk2 = real_signer()(msg)
    assert pk1 == pk2, "public key must be stable across signer instances"

    # Simulate a process restart: clear the in-process cache; the key must
    # reload from disk identically (the file was persisted on first use).
    monkeypatch.setattr(fc, "_CUTOVER_KEYPAIR", None)
    _sig3, pk3 = real_signer()(msg)
    assert pk3 == pk1, "public key must survive a restart (persisted to disk)"

    from omnix.receipts.verify import verify_bytes
    assert verify_bytes(pk1, msg, b"", sig1)


@pytest.fixture
def stub_controller():
    return FacadeController()  # no signer; receipts unsigned for routing-only tests


def test_initial_percentage_is_zero(controller):
    assert controller.state("t", "u").percentage == 0


def test_shift_with_clean_verifiers_authorizes(controller):
    event = controller.request_shift(
        tenant_id="t",
        unit_id="u",
        target_percentage=10,
        verifier_summary={
            "daikon_violated": 0,
            "scientist_mismatches": 0,
            "diffy_mismatches": 0,
            "hypothesis_passed": True,
        },
    )
    assert event.rejected_reason is None
    assert controller.state("t", "u").percentage == 10
    assert event.receipt_signature is not None
    assert event.receipt_payload is not None


def test_shift_blocked_on_verifier_mismatch(controller):
    event = controller.request_shift(
        tenant_id="t",
        unit_id="u",
        target_percentage=50,
        verifier_summary={
            "daikon_violated": 3,
            "scientist_mismatches": 0,
            "diffy_mismatches": 0,
            "hypothesis_passed": True,
        },
    )
    assert event.rejected_reason == "verifier_mismatch"
    assert controller.state("t", "u").percentage == 0


def test_full_lifecycle_progresses_then_rolls_back(controller):
    summary = {
        "daikon_violated": 0,
        "scientist_mismatches": 0,
        "diffy_mismatches": 0,
        "hypothesis_passed": True,
    }
    for pct in (10, 50, 100):
        ev = controller.request_shift(
            tenant_id="t", unit_id="u",
            target_percentage=pct,
            verifier_summary=summary,
        )
        assert ev.rejected_reason is None
        assert ev.receipt_signature is not None
    assert controller.state("t", "u").percentage == 100

    rb = controller.rollback(tenant_id="t", unit_id="u")
    assert rb.is_rollback
    assert rb.receipt_signature is not None
    assert controller.state("t", "u").percentage == 0
    assert len(controller.state("t", "u").history) == 4


def test_signed_payload_verifies_via_ml_dsa_65(controller):
    from omnix.receipts.verify import verify_bytes

    ev = controller.request_shift(
        tenant_id="t-bank", unit_id="payment-svc",
        target_percentage=10,
        verifier_summary={"daikon_violated": 0, "scientist_mismatches": 0,
                          "diffy_mismatches": 0, "hypothesis_passed": True},
    )
    assert verify_bytes(ev.public_key, ev.receipt_payload, b"", ev.receipt_signature)

    # Tampering breaks verification.
    tampered = ev.receipt_payload.replace(b"\"target_percentage\":10", b"\"target_percentage\":99")
    assert not verify_bytes(ev.public_key, tampered, b"", ev.receipt_signature)


def test_target_percentage_validation(controller):
    from omnix.cloud.cutover.facade_controller import CutoverError
    with pytest.raises(CutoverError):
        controller.request_shift(tenant_id="t", unit_id="u",
                                 target_percentage=150, verifier_summary={})


def test_cutover_api_round_trip():
    client = TestClient(create_app())
    token = issue("u-1", "tenant-A", "smb", "u@example.com")
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-Id": "tenant-A"}
    body = {
        "target_percentage": 10,
        "verifier_summary": {
            "daikon_violated": 0,
            "scientist_mismatches": 0,
            "diffy_mismatches": 0,
            "hypothesis_passed": True,
        },
    }
    r = client.post("/v1/cutover/payment-svc/shift", json=body, headers=headers)
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "authorized"

    state = client.get("/v1/cutover/payment-svc", headers=headers).json()
    assert state["percentage"] == 10

    rb = client.post("/v1/cutover/payment-svc/rollback", headers=headers)
    assert rb.json()["status"] == "rolled_back"
    state2 = client.get("/v1/cutover/payment-svc", headers=headers).json()
    assert state2["percentage"] == 0


def test_cutover_api_rejects_spoofed_tenant_header():
    client = TestClient(create_app())
    token = issue("u-1", "tenant-A", "smb", "u@example.com")
    headers = {"Authorization": f"Bearer {token}", "X-Tenant-Id": "tenant-B"}
    body = {"target_percentage": 10, "verifier_summary": {}}
    resp = client.post("/v1/cutover/payment-svc/shift", json=body, headers=headers)
    assert resp.status_code == 403
