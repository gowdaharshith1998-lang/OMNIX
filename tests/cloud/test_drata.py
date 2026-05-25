"""Drata integration tests."""

from __future__ import annotations

import base64
import hashlib

from omnix.cloud.compliance.drata import (
    FakeDrataTransport,
    list_supported_controls,
    push_evidence_for_receipts,
    receipt_to_evidence,
)


def test_receipt_to_evidence_round_trips_payload():
    payload = b'{"id":"r","kind":"replication"}'
    sha = hashlib.sha256(payload).hexdigest()
    evidence = receipt_to_evidence(
        receipt_kind="replication.behavioral",
        receipt_payload=payload,
        receipt_sha256=sha,
        control_id="CC7.2",
    )
    assert evidence.control_id == "CC7.2"
    assert base64.b64decode(evidence.payload_b64) == payload
    assert evidence.payload_sha256 == sha


def test_push_evidence_fans_out_one_per_control():
    transport = FakeDrataTransport()
    receipts = [
        {
            "receipt_kind": "replication.behavioral",  # 2 controls
            "payload": b'{"x":1}',
            "payload_sha256": "abc",
            "metadata": {},
        },
        {
            "receipt_kind": "rebuild.gate",   # 1 control
            "payload": b'{"y":2}',
            "payload_sha256": "def",
            "metadata": {},
        },
    ]
    ids = push_evidence_for_receipts(transport, receipts)
    assert len(ids) == 3
    assert len(transport.uploaded) == 3
    uploaded_controls = sorted(e.control_id for e in transport.uploaded)
    assert uploaded_controls == ["CC4.1", "CC7.2", "CC8.1"]


def test_unknown_receipt_kind_yields_no_uploads():
    transport = FakeDrataTransport()
    ids = push_evidence_for_receipts(
        transport,
        [{"receipt_kind": "future.kind", "payload": b"", "payload_sha256": ""}],
    )
    assert ids == []


def test_list_supported_controls_returns_mapping():
    mapping = list_supported_controls()
    assert "replication.behavioral" in mapping
    assert "CC7.2" in mapping["replication.behavioral"]
