"""Tests for the in-cluster observation collector service.

Covers the FastAPI surface that the Tetragon DaemonSet forwarder, Debezium
consumers, and mainframe bridges POST to.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from omnix.cloud.observe.collector_service import build_app
from omnix.cloud.observe.envelope import InMemorySink, ObservationKind


def _jsonl(*items: dict) -> bytes:
    return b"\n".join(json.dumps(i).encode() for i in items)


@pytest.fixture()
def sink() -> InMemorySink:
    return InMemorySink()


@pytest.fixture()
def client(sink: InMemorySink) -> TestClient:
    return TestClient(build_app(sink=sink))


def test_healthz_ok(client: TestClient) -> None:
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_metrics_exposes_counters(client: TestClient) -> None:
    r = client.get("/metrics")
    assert r.status_code == 200
    body = r.text
    assert "omnix_collector_tetragon_received" in body
    assert "omnix_collector_cdc_received" in body
    assert "omnix_collector_mainframe_received" in body


def test_ingest_tetragon_parses_via_existing_collector(
    client: TestClient, sink: InMemorySink
) -> None:
    body = _jsonl(
        {
            "pod": {"labels": {"omnix.io/observe": "true"}, "name": "api-7d"},
            "process_kprobe": {"function_name": "tcp_connect"},
            "node_name": "node-1",
        }
    )
    r = client.post("/v1/observe/tetragon", content=body)
    assert r.status_code == 200
    assert r.json() == {"accepted": 1}

    drained = sink.drain()
    assert len(drained) == 1
    assert drained[0].kind == ObservationKind.HTTP_REQUEST
    assert drained[0].pod == "api-7d"


def test_ingest_tetragon_namespace_filter_drops_event(sink: InMemorySink, tmp_path) -> None:
    filter_path = tmp_path / "filter.json"
    filter_path.write_text(json.dumps({"namespace_allow_list": ["omnix-prod"]}))
    app = build_app(sink=sink, filter_path=str(filter_path))
    client = TestClient(app)

    body = _jsonl(
        {
            "namespace": "other-tenant",
            "pod": {"labels": {"omnix.io/observe": "true"}},
            "process_kprobe": {"function_name": "tcp_connect"},
        }
    )
    r = client.post("/v1/observe/tetragon", content=body)
    assert r.status_code == 200
    assert r.json() == {"accepted": 0}
    assert sink.drain() == []


def test_ingest_tetragon_pii_redacted(client: TestClient, sink: InMemorySink) -> None:
    body = _jsonl(
        {
            "pod": {"labels": {"omnix.io/observe": "true"}, "name": "api-7d"},
            "process_kprobe": {"function_name": "tcp_connect"},
            "http_request": {"body": "user=alice@example.com from 10.0.0.5"},
        }
    )
    r = client.post("/v1/observe/tetragon", content=body)
    assert r.status_code == 200
    obs = sink.drain()[0]
    assert "<email>" in obs.payload["body"]
    assert "<ipv4>" in obs.payload["body"]


def test_ingest_cdc_parses_debezium_envelope(client: TestClient, sink: InMemorySink) -> None:
    body = _jsonl(
        {
            "payload": {
                "op": "c",
                "before": None,
                "after": {"id": 1, "email": "bob@example.com"},
                "source": {"db": "shop", "table": "orders", "ts_ms": 123},
            }
        }
    )
    r = client.post("/v1/observe/cdc", content=body)
    assert r.status_code == 200
    obs = sink.drain()
    assert len(obs) == 1
    assert obs[0].kind == ObservationKind.CDC_INSERT
    assert obs[0].service == "db://shop.orders"
    # PII redaction applied
    assert obs[0].payload["after"] == {"id": 1, "email": "<email>"}


def test_ingest_mainframe_routes_by_vendor_header(
    client: TestClient, sink: InMemorySink
) -> None:
    body = _jsonl({"smf_type": "30.4", "system_id": "SYS1", "job_name": "PAYROLL"})
    r = client.post(
        "/v1/observe/mainframe", content=body, headers={"x-omnix-vendor": "ironstream"}
    )
    assert r.status_code == 200
    assert r.json() == {"accepted": 1}
    obs = sink.drain()
    assert obs[0].kind == ObservationKind.MAINFRAME_JCL_JOB
    assert obs[0].service == "PAYROLL"


def test_ingest_mainframe_unknown_vendor_dropped(client: TestClient, sink: InMemorySink) -> None:
    body = _jsonl({"smf_type": "30.4"})
    r = client.post("/v1/observe/mainframe", content=body, headers={"x-omnix-vendor": "bogus"})
    assert r.status_code == 200
    assert r.json()["accepted"] == 0
    assert sink.drain() == []
