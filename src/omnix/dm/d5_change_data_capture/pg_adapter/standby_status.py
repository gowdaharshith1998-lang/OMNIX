"""Standby Status Update protocol (logical replication client → server).

Format ('r' message) per PG wire protocol:

  byte    'r'
  int64   write_lsn       (last LSN written to disk by the client)
  int64   flush_lsn       (last LSN flushed to disk by the client)
  int64   apply_lsn       (last LSN applied by the client)
  int64   client_clock    (microseconds since PG epoch 2000-01-01 UTC)
  byte    reply_requested (0/1)

Total payload = 1 + 8 + 8 + 8 + 8 + 1 = 34 bytes.
"""

from __future__ import annotations

import datetime
import struct
import threading
from typing import Any, Callable

_PG_EPOCH = datetime.datetime(2000, 1, 1, tzinfo=datetime.timezone.utc)


def _pg_microseconds_since_epoch(now: datetime.datetime | None = None) -> int:
    if now is None:
        now = datetime.datetime.now(datetime.timezone.utc)
    delta = now - _PG_EPOCH
    return int(delta.total_seconds() * 1_000_000)


def build_status_update(
    *,
    write_lsn: int,
    flush_lsn: int,
    apply_lsn: int,
    reply_requested: bool = False,
    now: datetime.datetime | None = None,
) -> bytes:
    return struct.pack(
        ">cQQQQB",
        b"r",
        write_lsn,
        flush_lsn,
        apply_lsn,
        _pg_microseconds_since_epoch(now),
        1 if reply_requested else 0,
    )


def send_status_update(
    conn: Any,
    *,
    write_lsn: int,
    flush_lsn: int,
    apply_lsn: int,
    reply_requested: bool = False,
) -> None:
    """Write a Standby Status Update to ``conn``. ``conn`` is a psycopg2
    LogicalReplicationConnection cursor whose ``send_feedback`` API takes the
    same fields (we surface a thin wrapper so tests can mock)."""
    cursor = conn.cursor()
    cursor.send_feedback(
        write_lsn=write_lsn,
        flush_lsn=flush_lsn,
        apply_lsn=apply_lsn,
        reply=reply_requested,
    )


class HeartbeatThread(threading.Thread):
    """Periodic standby-status heartbeat. ``get_flush_lsn`` is called on each
    tick to fetch the latest LSN the replayer has durably applied."""

    def __init__(
        self,
        *,
        send_callback: Callable[[int], None],
        get_flush_lsn: Callable[[], int],
        interval_sec: float = 10.0,
    ):
        super().__init__(daemon=True, name="omnix-dm-cdc-heartbeat")
        self._send = send_callback
        self._get = get_flush_lsn
        self._interval = interval_sec
        self._stop_event = threading.Event()

    def stop(self) -> None:
        self._stop_event.set()

    def run(self) -> None:
        while not self._stop_event.is_set():
            try:
                lsn = self._get()
                self._send(lsn)
            except Exception:
                # Heartbeat is best-effort; surface a metric in PR D.
                pass
            if self._stop_event.wait(self._interval):
                return


__all__ = [
    "build_status_update",
    "send_status_update",
    "HeartbeatThread",
]
