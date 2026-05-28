"""Standby status (heartbeat) protocol tests."""

from __future__ import annotations

import datetime
import struct
import threading
import time

import pytest

from omnix.dm.d5_change_data_capture.pg_adapter.standby_status import (
    HeartbeatThread,
    build_status_update,
)


def test_status_update_payload_is_34_bytes():
    payload = build_status_update(write_lsn=1, flush_lsn=2, apply_lsn=3)
    assert len(payload) == 34
    assert payload[0:1] == b"r"


def test_reply_requested_flag_encoded():
    a = build_status_update(write_lsn=0, flush_lsn=0, apply_lsn=0, reply_requested=True)
    b = build_status_update(write_lsn=0, flush_lsn=0, apply_lsn=0, reply_requested=False)
    assert a[-1] == 1
    assert b[-1] == 0


def test_lsns_round_trip_in_payload():
    payload = build_status_update(write_lsn=10, flush_lsn=20, apply_lsn=30)
    _, w, f, a, _, _ = struct.unpack(">cQQQQB", payload)
    assert (w, f, a) == (10, 20, 30)


def test_timestamp_is_postgres_epoch():
    fixed = datetime.datetime(2026, 5, 27, tzinfo=datetime.timezone.utc)
    payload = build_status_update(write_lsn=0, flush_lsn=0, apply_lsn=0, now=fixed)
    _, _, _, _, ts, _ = struct.unpack(">cQQQQB", payload)
    # Roughly 26 years of microseconds since 2000-01-01 (avoid leap-second pedantry)
    assert ts > (26 * 365 * 24 * 60 * 60) * 1_000_000


def test_heartbeat_thread_ticks_at_interval():
    sent_lsns = []
    stop_after_n = {"target": 2, "count": 0}
    cv = threading.Condition()

    def _send(lsn):
        with cv:
            sent_lsns.append(lsn)
            stop_after_n["count"] += 1
            cv.notify_all()

    def _get():
        return 999

    hb = HeartbeatThread(send_callback=_send, get_flush_lsn=_get, interval_sec=0.05)
    hb.start()
    deadline = time.monotonic() + 2.0
    with cv:
        while stop_after_n["count"] < 2 and time.monotonic() < deadline:
            cv.wait(timeout=0.1)
    hb.stop()
    hb.join(timeout=1.0)
    assert sent_lsns[:2] == [999, 999]
