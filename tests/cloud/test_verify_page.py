"""Public verifier page tests.

We mint a real ML-DSA-65 key pair, sign a payload, plant the descriptor into
the in-memory ReceiptStore, then exercise the HTML page, raw endpoints, and
the /api/verify endpoint.
"""

from __future__ import annotations

import base64
import hashlib
import json

import pytest
from fastapi.testclient import TestClient

from omnix.cloud.api.main import create_app
from omnix.cloud.verify_page.store import (
    ReceiptDescriptor,
    get_receipt_store,
)


@pytest.fixture
def signed_receipt():
    """Mint a real key pair + signed receipt. Skip if M0 receipts module is missing."""
    keygen = pytest.importorskip("omnix.receipts.keygen")
    sign_mod = pytest.importorskip("omnix.receipts.sign")
    pk, sk = keygen.keygen()

    payload = {"job_id": "job-abc", "result": "replicated", "target": "java21"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = sign_mod.sign_bytes(sk, canonical, b"", None)

    desc = ReceiptDescriptor(
        receipt_id="r-test-1",
        job_id="job-abc",
        receipt_kind="replication.behavioral",
        payload=payload,
        payload_canonical=canonical,
        payload_sha256=hashlib.sha256(canonical).hexdigest(),
        signature=sig,
        public_key=pk,
        created_at="2026-05-25T00:00:00Z",
    )
    store = get_receipt_store()
    store.clear()
    store.put(desc)
    yield desc
    store.clear()


@pytest.fixture
def client():
    return TestClient(create_app())


def test_render_receipt_html(client, signed_receipt):
    resp = client.get(f"/verify/r/{signed_receipt.receipt_id}")
    assert resp.status_code == 200, resp.text
    body = resp.text
    assert signed_receipt.receipt_id in body
    assert signed_receipt.job_id in body
    assert signed_receipt.payload_sha256 in body


def test_render_receipt_404(client):
    resp = client.get("/verify/r/no-such-receipt")
    assert resp.status_code == 404


def test_receipt_json_endpoint(client, signed_receipt):
    resp = client.get(f"/verify/r/{signed_receipt.receipt_id}.json")
    assert resp.status_code == 200
    assert resp.json() == signed_receipt.payload


def test_receipt_sig_endpoint(client, signed_receipt):
    resp = client.get(f"/verify/r/{signed_receipt.receipt_id}.sig")
    assert resp.status_code == 200
    assert resp.content == signed_receipt.signature


def test_pubkey_endpoint(client, signed_receipt):
    resp = client.get(f"/verify/pubkey/{signed_receipt.receipt_id}")
    assert resp.status_code == 200
    assert resp.content == signed_receipt.public_key


def test_api_verify_accepts_valid_signature(client, signed_receipt):
    payload = {
        "payload_canonical_b64": base64.b64encode(signed_receipt.payload_canonical).decode(),
        "signature_b64": base64.b64encode(signed_receipt.signature).decode(),
        "public_key_b64": base64.b64encode(signed_receipt.public_key).decode(),
    }
    resp = client.post("/verify/api/verify", json=payload)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["valid"] is True
    assert body["sha256"] == signed_receipt.payload_sha256


def test_api_verify_rejects_tampered_payload(client, signed_receipt):
    tampered = signed_receipt.payload_canonical.replace(b"replicated", b"tampered-x")
    payload = {
        "payload_canonical_b64": base64.b64encode(tampered).decode(),
        "signature_b64": base64.b64encode(signed_receipt.signature).decode(),
        "public_key_b64": base64.b64encode(signed_receipt.public_key).decode(),
    }
    resp = client.post("/verify/api/verify", json=payload)
    assert resp.status_code == 200
    assert resp.json()["valid"] is False


def test_wasm_loader_returns_javascript(client):
    resp = client.get("/verify/wasm/verify.js")
    assert resp.status_code == 200
    assert "__omnix_verify" in resp.text
