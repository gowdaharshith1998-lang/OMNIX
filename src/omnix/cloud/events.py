"""Job-event bus.

Production: Redis pubsub on channel ``job:{job_id}:events``.
Tests: an in-process fanout that mirrors the Redis surface.

Event envelope:
    {
        "job_id":   "<uuid>",
        "seq":      <int>,
        "gate":     "ingest" | "parse" | "spec" | "generate" | "verify" | "cutover" | "complete" | "error",
        "severity": "info" | "warn" | "error" | "success",
        "message":  "<human-readable>",
        "payload":  { ... },
        "ts":       "<iso8601>"
    }
"""

from __future__ import annotations

import asyncio
import json
import threading
from collections import defaultdict
from collections.abc import AsyncIterator
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass
class JobEvent:
    job_id: str
    seq: int
    gate: str | None
    severity: str
    message: str
    payload: dict[str, Any] = field(default_factory=dict)
    ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_json(self) -> str:
        return json.dumps(asdict(self))

    @classmethod
    def from_json(cls, raw: str) -> "JobEvent":
        return cls(**json.loads(raw))


class _InMemoryBus:
    """Simple fan-out used in tests and single-process dev.

    The async-subscriber API mirrors the redis aio pubsub surface so that the
    WebSocket router can switch backends by flag.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._subscribers: dict[str, list[asyncio.Queue]] = defaultdict(list)
        self._history: dict[str, list[JobEvent]] = defaultdict(list)
        self._seq: dict[str, int] = defaultdict(int)

    def next_seq(self, job_id: str) -> int:
        with self._lock:
            self._seq[job_id] += 1
            return self._seq[job_id]

    def publish(self, event: JobEvent) -> None:
        with self._lock:
            self._history[event.job_id].append(event)
            qs = list(self._subscribers.get(event.job_id, ()))
        for q in qs:
            try:
                q.put_nowait(event)
            except asyncio.QueueFull:  # pragma: no cover
                pass

    def history(self, job_id: str) -> list[JobEvent]:
        with self._lock:
            return list(self._history.get(job_id, []))

    async def subscribe(self, job_id: str, *, replay: bool = True) -> AsyncIterator[JobEvent]:
        q: asyncio.Queue[JobEvent] = asyncio.Queue(maxsize=1024)
        with self._lock:
            self._subscribers[job_id].append(q)
        if replay:
            for event in self.history(job_id):
                await q.put(event)
        try:
            while True:
                ev = await q.get()
                yield ev
        finally:
            with self._lock:
                if q in self._subscribers.get(job_id, []):
                    self._subscribers[job_id].remove(q)


_BUS = _InMemoryBus()


def publish(job_id: str, gate: str | None, message: str, *,
            severity: str = "info", payload: dict[str, Any] | None = None) -> JobEvent:
    payload = payload or {}
    # Durable, cross-process seq + persistence when enabled; otherwise the
    # in-process counter. The DB is authoritative for seq so two processes
    # publishing for the same job don't collide.
    durable_seq: int | None = None
    try:
        from omnix.cloud import store

        event_ts = datetime.now(timezone.utc).isoformat()
        durable_seq = store.next_seq_and_persist(
            job_id=job_id, gate=gate, severity=severity,
            message=message, payload=payload, ts=event_ts,
        )
    except Exception:  # noqa: BLE001 - never let persistence break the live path
        durable_seq = None

    event = JobEvent(
        job_id=job_id,
        seq=durable_seq if durable_seq is not None else _BUS.next_seq(job_id),
        gate=gate,
        severity=severity,
        message=message,
        payload=payload,
    )
    _BUS.publish(event)
    return event


def history(job_id: str) -> list[JobEvent]:
    """Durable history when persistence is on (visible across processes),
    else the in-process bus."""
    try:
        from omnix.cloud import store

        rows = store.load_events(job_id)
        if rows is not None:
            return [
                JobEvent(
                    job_id=r["job_id"], seq=r["seq"], gate=r["gate"],
                    severity=r["severity"], message=r["message"],
                    payload=r.get("payload") or {},
                    ts=r.get("ts") or datetime.now(timezone.utc).isoformat(),
                )
                for r in rows
            ]
    except Exception:  # noqa: BLE001
        pass
    return _BUS.history(job_id)


async def subscribe(job_id: str, *, replay: bool = True) -> AsyncIterator[JobEvent]:
    async for ev in _BUS.subscribe(job_id, replay=replay):
        yield ev


def reset_bus() -> None:
    """Test hook — drop all subscribers + history."""
    global _BUS
    _BUS = _InMemoryBus()
