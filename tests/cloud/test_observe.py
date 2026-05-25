"""Observation collector tests."""

from __future__ import annotations

import json

from omnix.cloud.observe import InMemorySink, ObservationKind
from omnix.cloud.observe.cdc_collector import collect_cdc
from omnix.cloud.observe.envelope import redact
from omnix.cloud.observe.mainframe_collector import (
    collect_cics,
    collect_smf,
    collect_vsam,
)
from omnix.cloud.observe.tetragon_collector import collect_events


def test_redact_email_and_pan():
    payload = {"email": "alice@bank.com", "card": "4111 1111 1111 1111"}
    out, fields = redact(payload)
    assert out["email"] == "<email>"
    assert out["card"] == "<pan>"
    assert "email" in fields
    assert "card" in fields


def test_tetragon_filters_unlabeled_pods():
    events = [
        {"http_request": {"path": "/x"}, "pod": {"name": "p1", "labels": {}}},
        {"http_request": {"path": "/y"}, "pod": {"name": "p2", "labels": {"omnix.io/observe": "true"}}},
    ]
    sink = collect_events(events)
    items = sink.drain()
    assert len(items) == 1
    assert items[0].pod == "p2"


def test_tetragon_emits_http_kind():
    events = [{"http_request": {"path": "/foo", "method": "GET"}, "pod": {"labels": {"omnix.io/observe": "true"}, "name": "p"}}]
    sink = collect_events(events)
    items = sink.drain()
    assert items[0].kind == ObservationKind.HTTP_REQUEST


def test_tetragon_redacts_pii():
    events = [{"http_request": {"path": "/q", "body": "email=alice@bank.com"},
               "pod": {"name": "p", "labels": {"omnix.io/observe": "true"}}}]
    sink = collect_events(events)
    items = sink.drain()
    assert "<email>" in str(items[0].payload)
    assert items[0].redacted_fields


def test_cdc_routes_op_to_kind():
    events = [
        {"payload": {"op": "c", "after": {"id": 1}, "source": {"db": "appdb", "table": "users"}}},
        {"payload": {"op": "u", "after": {"id": 1, "name": "x"}, "before": {"id": 1}, "source": {"db": "appdb", "table": "users"}}},
        {"payload": {"op": "d", "before": {"id": 1}, "source": {"db": "appdb", "table": "users"}}},
    ]
    sink = collect_cdc(events)
    items = sink.drain()
    assert [i.kind for i in items] == [
        ObservationKind.CDC_INSERT,
        ObservationKind.CDC_UPDATE,
        ObservationKind.CDC_DELETE,
    ]
    assert items[0].service == "db://appdb.users"


def test_cdc_redacts_pii_in_before_after():
    events = [{"payload": {"op": "u", "before": {"email": "x@y.com"}, "after": {"email": "z@y.com"}, "source": {"db": "d", "table": "t"}}}]
    sink = collect_cdc(events)
    items = sink.drain()
    assert items[0].payload["after"]["email"] == "<email>"
    assert items[0].redacted_fields


def test_smf_filters_to_type_30_4():
    events = [
        {"smf_type": "30.4", "job_name": "JOB1", "system_id": "SYS1"},
        {"smf_type": "70.1", "job_name": "JOBX"},
    ]
    sink = collect_smf(events)
    items = sink.drain()
    assert len(items) == 1
    assert items[0].kind == ObservationKind.MAINFRAME_JCL_JOB
    assert items[0].service == "JOB1"


def test_cics_and_vsam_collectors():
    sink = collect_cics([{"region": "CICSPROD", "transaction_id": "INQ1"}])
    items = sink.drain()
    assert items[0].kind == ObservationKind.MAINFRAME_CICS_TXN
    assert items[0].service == "INQ1"

    sink = collect_vsam([{"system_id": "SYS1", "dataset": "PROD.VSAM.FILE", "op": "PUT"}])
    items = sink.drain()
    assert items[0].kind == ObservationKind.MAINFRAME_VSAM_OP
    assert items[0].service == "PROD.VSAM.FILE"


def test_observations_carry_capture_time_and_envelope():
    sink = InMemorySink()
    collect_events(
        [{"http_request": {"path": "/x"}, "pod": {"name": "p", "labels": {"omnix.io/observe": "true"}}}],
        sink=sink,
    )
    obs = sink.drain()[0]
    assert obs.captured_at > 0
