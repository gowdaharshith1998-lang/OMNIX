"""Cross-pod cutover event bus.

Two implementations:

- ``InMemoryCutoverBus`` — single-process pub/sub. The default. Used by
  tests and for single-replica deployments where no Redis is available.
- ``RedisStreamsCutoverBus`` — cross-pod broadcast over Redis Streams.
  The controller XADDs every authorized shift; the facade_writer_runner
  XREADs and drives Envoy. Streams (not pub/sub) give us a history that
  resumes via ``Last-Event-ID`` after a writer-sidecar restart.

The public surface is intentionally tiny:

    bus.publish(event_id, payload)             # sync, called from controller
    async for ev_id, payload in bus.subscribe(last_event_id):  # SSE endpoint

Why publish is sync: the controller's ``_notify_writers`` is called inside
its RLock and the existing in-process subscribers are sync. Keeping the bus
publish sync preserves that contract — the bus does its own thread-safe
loop hand-off via ``call_soon_threadsafe``.
"""

from __future__ import annotations

import asyncio
import json
import logging
import threading
from collections import deque
from collections.abc import AsyncIterator
from typing import Protocol

log = logging.getLogger("omnix.cloud.cutover.event_bus")


class CutoverBus(Protocol):
    """Minimal contract every cutover bus implements."""

    def publish(self, event_id: str, payload: dict) -> None: ...

    def subscribe(self, last_event_id: str | None = None) -> AsyncIterator[tuple[str, dict]]: ...


class InMemoryCutoverBus:
    """Single-process bus backed by a bounded ring buffer.

    ``publish`` is sync (no asyncio loop required). ``subscribe`` is an
    async generator that yields ``(event_id, payload)`` tuples and supports
    ``last_event_id`` replay from history.
    """

    HISTORY_MAX = 1024

    def __init__(self, history_max: int | None = None) -> None:
        self._lock = threading.Lock()
        self._history: deque[tuple[str, dict]] = deque(
            maxlen=history_max if history_max is not None else self.HISTORY_MAX
        )
        # Each subscriber registers as (loop, queue) so publish from any
        # thread can safely deliver via call_soon_threadsafe.
        self._subscribers: list[tuple[asyncio.AbstractEventLoop, asyncio.Queue]] = []

    def publish(self, event_id: str, payload: dict) -> None:
        snap = dict(payload)
        with self._lock:
            self._history.append((event_id, snap))
            subs = list(self._subscribers)
        for loop, q in subs:
            try:
                loop.call_soon_threadsafe(self._enqueue_or_drop, q, (event_id, dict(snap)))
            except RuntimeError:
                # Subscriber's loop has been closed; ignore.
                pass

    @staticmethod
    def _enqueue_or_drop(q: asyncio.Queue, item: tuple[str, dict]) -> None:
        try:
            q.put_nowait(item)
        except asyncio.QueueFull:
            # Slow subscriber — drop oldest, append newest.
            try:
                q.get_nowait()
            except asyncio.QueueEmpty:
                pass
            try:
                q.put_nowait(item)
            except asyncio.QueueFull:
                pass

    async def subscribe(
        self, last_event_id: str | None = None
    ) -> AsyncIterator[tuple[str, dict]]:
        loop = asyncio.get_running_loop()
        q: asyncio.Queue = asyncio.Queue(maxsize=1024)

        # Replay every entry that came AFTER last_event_id (the client has
        # already seen everything up to and including that id).
        with self._lock:
            if last_event_id is not None:
                seen = False
                for ev_id, payload in self._history:
                    if seen:
                        try:
                            q.put_nowait((ev_id, dict(payload)))
                        except asyncio.QueueFull:
                            break
                    if ev_id == last_event_id:
                        seen = True
            self._subscribers.append((loop, q))

        try:
            while True:
                item = await q.get()
                yield item
        finally:
            with self._lock:
                self._subscribers = [s for s in self._subscribers if s[1] is not q]

    def reset(self) -> None:
        """Test hook — drop all history and subscribers."""
        with self._lock:
            self._history.clear()
            self._subscribers.clear()

    def history_snapshot(self) -> list[tuple[str, dict]]:
        """For tests: return a copy of the current history."""
        with self._lock:
            return [(ev_id, dict(payload)) for ev_id, payload in self._history]


class RedisStreamsCutoverBus:
    """Cross-pod broadcast over a single Redis Stream key.

    Idempotency: ``FacadeWriter.apply_event`` is idempotent — applying the
    same target_percentage twice produces the same routes.json byte-for-byte
    — so we use plain XREAD (no consumer groups) and accept at-least-once.

    Publish uses sync ``redis-py`` (called from the controller, which is sync).
    Subscribe uses ``redis.asyncio`` (called from the FastAPI SSE handler).
    """

    STREAM_KEY = "omnix:cutover:events"
    READ_BLOCK_MS = 15_000
    READ_COUNT = 16

    def __init__(self, redis_url: str) -> None:
        import redis  # local import keeps redis optional
        import redis.asyncio as aioredis

        self._url = redis_url
        self._sync = redis.from_url(redis_url, decode_responses=True)
        self._async = aioredis.from_url(redis_url, decode_responses=True)

    def publish(self, event_id: str, payload: dict) -> None:
        try:
            self._sync.xadd(
                self.STREAM_KEY,
                {"event_id": event_id, "payload": json.dumps(payload)},
            )
        except Exception:  # noqa: BLE001
            log.exception("RedisStreamsCutoverBus.publish failed")

    async def subscribe(
        self, last_event_id: str | None = None
    ) -> AsyncIterator[tuple[str, dict]]:
        # XREAD with `$` reads only new entries; with a real id, resumes from
        # the next entry. Streams ids are server-assigned strings like
        # "1716580000000-0"; the controller's event_id is uuid hex — we map
        # via the entry's own id so resume works.
        last_id = last_event_id or "$"
        while True:
            try:
                resp = await self._async.xread(
                    {self.STREAM_KEY: last_id},
                    block=self.READ_BLOCK_MS,
                    count=self.READ_COUNT,
                )
            except Exception:  # noqa: BLE001
                log.exception("xread failed; retrying in 1s")
                await asyncio.sleep(1.0)
                continue
            if not resp:
                continue
            for _stream_name, entries in resp:
                for entry_id, fields in entries:
                    last_id = entry_id
                    try:
                        payload = json.loads(fields.get("payload", "{}"))
                    except json.JSONDecodeError:
                        continue
                    ev_id = fields.get("event_id") or entry_id
                    yield ev_id, payload
