"""Lag monitor tests (P11)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm.d5_change_data_capture.cdc_replayer import CDCReplayState
from omnix.dm.d5_change_data_capture.lag_monitor import LagMonitor


@pytest.fixture
def keys():
    return ml_dsa_65.keypair(seed=b"\xff" * 48)


def _monitor(tmp_path, keys, *, legacy="0/1000", target="0/100", legacy_raises=False, target_raises=False):
    pk, sk = keys
    replay = CDCReplayState(migration_id="m1")

    def _legacy():
        if legacy_raises:
            raise RuntimeError("connection refused")
        return legacy

    def _target():
        if target_raises:
            raise RuntimeError("connection refused")
        return target

    return LagMonitor(
        migration_id="m1",
        replay_state=replay,
        output_root=tmp_path,
        secret_key=sk,
        public_key=pk,
        legacy_lsn_provider=_legacy,
        target_lsn_provider=_target,
        bytes_per_second_estimate=1_000.0,
    )


def test_happy_lag_calculation(tmp_path, keys):
    m = _monitor(tmp_path, keys, legacy="0/1000", target="0/100")
    r = m.tick()
    assert r.legacy_unreachable is False
    assert r.target_unreachable is False
    assert r.lag_lsn_bytes == 0xF00
    assert r.lag_estimated_seconds is not None


def test_legacy_unreachable_surfaces_honestly(tmp_path, keys):
    m = _monitor(tmp_path, keys, legacy_raises=True)
    r = m.tick()
    assert r.legacy_unreachable is True
    assert r.lag_lsn_bytes is None
    assert r.lag_estimated_seconds is None


def test_target_unreachable_surfaces_honestly(tmp_path, keys):
    m = _monitor(tmp_path, keys, target_raises=True)
    r = m.tick()
    assert r.target_unreachable is True
    assert r.lag_lsn_bytes is None


def test_interval_event_counters_advance(tmp_path, keys):
    m = _monitor(tmp_path, keys)
    m.replay_state.events_replayed = 10
    r1 = m.tick()
    assert r1.events_replayed_last_interval == 10
    m.replay_state.events_replayed = 17
    r2 = m.tick()
    assert r2.events_replayed_last_interval == 7


def test_unhandled_event_types_accumulate_monotonically(tmp_path, keys):
    m = _monitor(tmp_path, keys)
    m.replay_state.unhandled_event_types = ["Truncate"]
    r1 = m.tick()
    assert "Truncate" in r1.unhandled_event_types_seen
    m.replay_state.unhandled_event_types = []  # clears upstream; report keeps it
    r2 = m.tick()
    assert "Truncate" in r2.unhandled_event_types_seen


def test_lag_report_written_signed(tmp_path, keys):
    m = _monitor(tmp_path, keys)
    m.tick()
    reports = list((tmp_path / "m1" / "d5").glob("lag-report-*.json"))
    assert len(reports) == 1
    sig_path = reports[0].parent / (reports[0].name + ".sig")
    assert sig_path.exists()
