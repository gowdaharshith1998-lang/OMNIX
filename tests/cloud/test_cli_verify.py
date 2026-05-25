"""End-to-end CLI verify test.

We boot the FastAPI app via TestClient with a planted signed receipt, then point the
CLI at the in-process URL via a small monkeypatched _fetch helper.
"""

from __future__ import annotations

import base64
import hashlib
import json

import pytest

from omnix.cloud import cli_verify
from omnix.cloud.api.main import create_app
from omnix.cloud.verify_page.store import (
    ReceiptDescriptor,
    get_receipt_store,
)


@pytest.fixture
def planted_receipt(monkeypatch):
    keygen = pytest.importorskip("omnix.receipts.keygen")
    sign_mod = pytest.importorskip("omnix.receipts.sign")
    pk, sk = keygen.keygen()
    payload = {"id": "r-cli", "result": "ok"}
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    sig = sign_mod.sign_bytes(sk, canonical, b"", None)
    desc = ReceiptDescriptor(
        receipt_id="r-cli",
        job_id="j",
        receipt_kind="replication",
        payload=payload,
        payload_canonical=canonical,
        payload_sha256=hashlib.sha256(canonical).hexdigest(),
        signature=sig,
        public_key=pk,
        created_at="2026-05-25T00:00:00Z",
    )
    get_receipt_store().clear()
    get_receipt_store().put(desc)

    from fastapi.testclient import TestClient

    client = TestClient(create_app())

    def fake_fetch(url: str) -> bytes:
        path = url.split("//", 1)[-1].split("/", 1)[1]
        resp = client.get("/" + path)
        resp.raise_for_status()
        return resp.content

    monkeypatch.setattr(cli_verify, "_fetch", fake_fetch)
    yield desc
    get_receipt_store().clear()


def test_cli_verify_returns_zero_on_valid(planted_receipt, capsys):
    rc = cli_verify.main(["http://localhost/verify/r/r-cli"])
    out = capsys.readouterr().out
    assert rc == 0
    assert out.startswith("OK")
    assert planted_receipt.payload_sha256 in out


def test_cli_verify_returns_one_on_tampered(planted_receipt, monkeypatch, capsys):
    original_fetch = cli_verify._fetch

    def tampered(url: str) -> bytes:
        body = original_fetch(url)
        if url.endswith(".json"):
            # Re-encode the payload with one field flipped.
            data = json.loads(body)
            data["result"] = "tampered"
            return json.dumps(data).encode()
        return body

    monkeypatch.setattr(cli_verify, "_fetch", tampered)
    rc = cli_verify.main(["http://localhost/verify/r/r-cli"])
    err = capsys.readouterr().err
    assert rc == 1
    assert "FAIL" in err
