"""Cilium Tetragon (eBPF) collector.

Subscribes to Tetragon's JSON-line output, filters to OMNIX-scoped pods,
redacts PII, and forwards Observations to the configured sink.

Production wires this to Tetragon's unix socket / tcp endpoint via grpc.
For tests we accept an iterable of JSON-lines so the same code path is
exercised with deterministic fixtures.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from omnix.cloud.observe.envelope import (
    InMemorySink,
    Observation,
    ObservationKind,
    ObservationSink,
    redact,
)

OMNIX_LABEL = "omnix.io/observe"


def _kind_from_event(event: dict[str, Any]) -> ObservationKind | None:
    if "process_kprobe" in event:
        fn = event["process_kprobe"].get("function_name", "")
        if "tcp" in fn or "http" in fn:
            return ObservationKind.HTTP_REQUEST
        if "exec" in fn:
            return ObservationKind.SYSCALL_EXEC
        if "open" in fn:
            return ObservationKind.FILE_OPEN
    if "process_dns" in event:
        return ObservationKind.DNS_LOOKUP
    if "process_exec" in event:
        return ObservationKind.SYSCALL_EXEC
    if "http_request" in event:
        return ObservationKind.HTTP_REQUEST
    if "sql_query" in event:
        return ObservationKind.SQL_QUERY
    return None


def _pod_observable(event: dict[str, Any]) -> bool:
    labels = (
        event.get("pod", {}).get("labels")
        or event.get("process", {}).get("pod", {}).get("labels")
        or {}
    )
    return labels.get(OMNIX_LABEL) == "true"


def _pod_name(event: dict[str, Any]) -> str | None:
    return (
        event.get("pod", {}).get("name")
        or event.get("process", {}).get("pod", {}).get("name")
    )


def collect_events(
    events: Iterable[str | dict],
    *,
    sink: ObservationSink | None = None,
    require_label: bool = True,
) -> ObservationSink:
    """Drain an iterable of Tetragon JSONL events into an ObservationSink."""
    if sink is None:
        sink = InMemorySink()

    for raw in events:
        event = json.loads(raw) if isinstance(raw, str) else dict(raw)
        if require_label and not _pod_observable(event):
            continue
        kind = _kind_from_event(event)
        if kind is None:
            continue

        payload_in = event.get("http_request") or event.get("sql_query") or event
        redacted_payload, redacted_fields = redact(payload_in)

        sink.absorb(
            Observation(
                kind=kind,
                pod=_pod_name(event),
                node=event.get("node_name"),
                service=event.get("service") or event.get("destination", {}).get("service"),
                payload=redacted_payload,
                redacted_fields=tuple(redacted_fields),
            )
        )
    return sink
