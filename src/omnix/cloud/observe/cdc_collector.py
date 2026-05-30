"""Debezium CDC collector.

Drains Kafka topics that Debezium publishes (one per source table) into
Observation rows. The Kafka client is injectable so tests can drive the
collector with an iterable.
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

_OP_TO_KIND = {
    "c": ObservationKind.CDC_INSERT,
    "u": ObservationKind.CDC_UPDATE,
    "d": ObservationKind.CDC_DELETE,
}


def collect_cdc(
    events: Iterable[str | dict],
    *,
    sink: ObservationSink | None = None,
) -> ObservationSink:
    """Drain Debezium-style messages into a sink.

    Each event must be a Debezium envelope:
      {
        "payload": {
          "op": "c"|"u"|"d",
          "before": {...},
          "after":  {...},
          "source": {"db": "...", "table": "...", "ts_ms": 1234}
        }
      }
    """
    if sink is None:
        sink = InMemorySink()

    for raw in events:
        event = json.loads(raw) if isinstance(raw, str) else dict(raw)
        payload = event.get("payload") or event
        op = payload.get("op")
        kind = _OP_TO_KIND.get(op)
        if kind is None:
            continue

        source = payload.get("source", {})
        redacted_before, before_fields = redact(payload.get("before") or {})
        redacted_after, after_fields = redact(payload.get("after") or {})
        obs = Observation(
            kind=kind,
            pod=None,
            node=None,
            service=f"db://{source.get('db','?')}.{source.get('table','?')}",
            payload={
                "op": op,
                "before": redacted_before,
                "after": redacted_after,
                "source": source,
            },
            redacted_fields=tuple(before_fields) + tuple(after_fields),
        )
        sink.absorb(obs)
    return sink
