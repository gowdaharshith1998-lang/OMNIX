"""Mainframe bridges.

Routes SMF/SYSLOG (Ironstream), tcVISION VSAM/Db2, and C\\Prof CICS internal
trace into the same Observation envelope.

This module is the bridge surface — real wire format is captured per source
via Confluent Kafka topics. For tests, an iterable of dicts is sufficient.
"""

from __future__ import annotations

import json
from collections.abc import Iterable

from omnix.cloud.observe.envelope import (
    InMemorySink,
    Observation,
    ObservationKind,
    ObservationSink,
)


def collect_smf(events: Iterable[str | dict], *,
                sink: ObservationSink | None = None) -> ObservationSink:
    """SMF (System Management Facility) records — type 30.4 = job summary."""
    if sink is None:
        sink = InMemorySink()
    for raw in events:
        event = json.loads(raw) if isinstance(raw, str) else dict(raw)
        if str(event.get("smf_type", "")) != "30.4":
            continue
        sink.absorb(Observation(
            kind=ObservationKind.MAINFRAME_JCL_JOB,
            pod=None, node=event.get("system_id"),
            service=event.get("job_name"),
            payload=event,
        ))
    return sink


def collect_cics(events: Iterable[str | dict], *,
                 sink: ObservationSink | None = None) -> ObservationSink:
    """C\\Prof CICS internal-trace events."""
    if sink is None:
        sink = InMemorySink()
    for raw in events:
        event = json.loads(raw) if isinstance(raw, str) else dict(raw)
        sink.absorb(Observation(
            kind=ObservationKind.MAINFRAME_CICS_TXN,
            pod=None, node=event.get("region"),
            service=event.get("transaction_id"),
            payload=event,
        ))
    return sink


def collect_vsam(events: Iterable[str | dict], *,
                 sink: ObservationSink | None = None) -> ObservationSink:
    """PowerExchange ECCR + tcVISION VSAM events."""
    if sink is None:
        sink = InMemorySink()
    for raw in events:
        event = json.loads(raw) if isinstance(raw, str) else dict(raw)
        sink.absorb(Observation(
            kind=ObservationKind.MAINFRAME_VSAM_OP,
            pod=None, node=event.get("system_id"),
            service=event.get("dataset"),
            payload=event,
        ))
    return sink
