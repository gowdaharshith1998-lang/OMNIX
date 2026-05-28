"""Cutover proposal tests (P11)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm._types import LagReport, ParityMetric
from omnix.dm.d5_change_data_capture.cutover_proposal_emitter import (
    CutoverState,
    emit_proposal,
    evaluate,
)
from omnix.dm.receipts.ml_dsa_65_signer import verify_canonical


@pytest.fixture
def keys():
    return ml_dsa_65.keypair(seed=b"\x12" * 48)


def _lag(reachable=True, lag_seconds=1.0):
    return LagReport(
        migration_id="m1",
        timestamp="2026-05-27T00:00:00+00:00",
        legacy_current_lsn="0/1000",
        target_applied_lsn="0/900",
        legacy_unreachable=not reachable,
        target_unreachable=not reachable,
        lag_lsn_bytes=100,
        lag_estimated_seconds=lag_seconds,
        events_replayed_last_interval=10,
        events_quarantined_last_interval=0,
        unhandled_event_types_seen=(),
    )


def test_sustained_window_required_before_proposal():
    state = CutoverState(sustained_window_required_sec=10)
    # First tick: starts the window, no proposal yet
    assert evaluate(state=state, lag_report=_lag(), now_monotonic=100.0) is None
    # Second tick within window
    assert evaluate(state=state, lag_report=_lag(), now_monotonic=105.0) is None
    # Third tick after window
    proposal = evaluate(state=state, lag_report=_lag(), now_monotonic=115.0)
    assert proposal is not None
    assert proposal.recommended_action == "operator_sign"
    assert proposal.parity_not_met is False


def test_lag_spike_resets_window():
    state = CutoverState(sustained_window_required_sec=5)
    assert evaluate(state=state, lag_report=_lag(lag_seconds=1.0), now_monotonic=0.0) is None
    # lag spike — clears window
    assert (
        evaluate(state=state, lag_report=_lag(lag_seconds=120.0), now_monotonic=2.0)
        is None
    )
    assert state.sustained_window_start is None


def test_high_divergence_returns_investigate_action():
    state = CutoverState(parity_threshold=0.0001)
    metrics = [
        ParityMetric(table="owners", rows_compared=10_000, rows_diverged=10, divergence_rate=0.001)
    ]
    proposal = evaluate(
        state=state, lag_report=_lag(), parity_metrics=metrics, now_monotonic=0.0
    )
    assert proposal is not None
    assert proposal.parity_not_met is True
    assert proposal.recommended_action == "investigate_divergence"


def test_proposal_predecessor_hash_set_on_emit(tmp_path, keys):
    pk, sk = keys
    state = CutoverState(sustained_window_required_sec=0)
    proposal = evaluate(
        state=state, lag_report=_lag(), now_monotonic=0.0
    )
    assert proposal is None  # first tick starts window
    proposal = evaluate(state=state, lag_report=_lag(), now_monotonic=1.0)
    assert proposal is not None
    pred = hashlib.sha256(b"d2").hexdigest()
    path = emit_proposal(
        proposal,
        predecessor_hash=pred,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    payload = json.loads(path.read_text())
    assert payload["predecessor_hash"] == pred


def test_proposal_signature_verifies(tmp_path, keys):
    pk, sk = keys
    state = CutoverState(sustained_window_required_sec=0)
    evaluate(state=state, lag_report=_lag(), now_monotonic=0.0)
    proposal = evaluate(state=state, lag_report=_lag(), now_monotonic=1.0)
    pred = hashlib.sha256(b"d2").hexdigest()
    path = emit_proposal(
        proposal,
        predecessor_hash=pred,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    sig = (path.parent / (path.name + ".sig")).read_text()
    payload = json.loads(path.read_text())
    assert verify_canonical(payload, sig, pk)


def test_unreachable_legacy_blocks_proposal():
    state = CutoverState(sustained_window_required_sec=0)
    proposal = evaluate(
        state=state,
        lag_report=_lag(reachable=False),
        now_monotonic=0.0,
    )
    assert proposal is None
