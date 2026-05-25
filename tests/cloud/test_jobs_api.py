"""Replication-jobs REST + WebSocket tests.

The `inline=True` mode runs the runner synchronously in dry_run, exercising
the gate progression without needing Celery.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from omnix.cloud import events
from omnix.cloud.api.main import create_app


@pytest.fixture(autouse=True)
def _reset_bus():
    events.reset_bus()
    yield
    events.reset_bus()


@pytest.fixture
def client():
    return TestClient(create_app())


def test_start_job_inline_dry_run(client):
    resp = client.post(
        "/v1/jobs",
        json={"source": {"workspace": "/tmp/example"}, "inline": True},
    )
    assert resp.status_code == 202
    body = resp.json()
    assert body["job_id"]
    assert body["state"] == "awaiting_cutover"

    status = client.get(f"/v1/jobs/{body['job_id']}")
    assert status.status_code == 200
    gates_seen = {ev["gate"] for ev in status.json()["events"]}
    assert "ingest" in gates_seen
    assert "verify" in gates_seen
    assert "cutover" in gates_seen


def test_job_status_404_on_unknown_id(client):
    resp = client.get("/v1/jobs/nonexistent-id-xyz")
    assert resp.status_code == 404


def test_list_events_since_seq(client):
    resp = client.post(
        "/v1/jobs",
        json={"source": {"workspace": "/tmp/x"}, "inline": True},
    )
    job_id = resp.json()["job_id"]
    all_events = client.get(f"/v1/jobs/{job_id}/events").json()
    assert len(all_events) >= 4

    half = all_events[len(all_events) // 2]
    tail = client.get(
        f"/v1/jobs/{job_id}/events", params={"since_seq": half["seq"]}
    ).json()
    assert all(ev["seq"] > half["seq"] for ev in tail)


def test_websocket_streams_replayed_events(client):
    resp = client.post(
        "/v1/jobs",
        json={"source": {"workspace": "/tmp/y"}, "inline": True},
    )
    job_id = resp.json()["job_id"]

    received: list[dict] = []
    with client.websocket_connect(f"/ws/jobs/{job_id}") as ws:
        for _ in range(5):
            received.append(ws.receive_json())

    assert all(ev["type"] == "gate_event" for ev in received)
    gates = {ev["gate"] for ev in received}
    assert {"ingest", "parse", "spec", "generate", "verify"} & gates
