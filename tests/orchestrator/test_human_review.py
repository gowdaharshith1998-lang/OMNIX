"""Tests for omnix.orchestrator.human_review — HumanReviewRecord + RetryRunReport."""

from __future__ import annotations

import dataclasses
import json

import pytest

from omnix.gates.result import GateError, GateResult
from omnix.orchestrator.attempt import RebuildAttempt
from omnix.orchestrator.human_review import HumanReviewRecord, RetryRunReport


def _make_attempt(fqn: str, n: int) -> RebuildAttempt:
    return RebuildAttempt(
        node_fqn=fqn,
        spec_hash=f"spec{n}",
        prompt_template_version="1.0.0",
        prompt_text_hash=f"prompt{n}",
        response_text=f"response{n}",
        timestamp=RebuildAttempt.now_utc(),
        model="claude-opus-4.7",
        attempt_number=n,
    )


def _make_failing_result(n: int) -> GateResult:
    return GateResult(
        gate1_passed=False,
        gate2_passed=True,
        gate3_passed=True,
        gate4_passed=True,
        gate1_error=GateError(
            gate_number=1,
            gate_name="gate1_syntactic",
            message=f"failure {n}",
            details={"i": n},
        ),
    )


def _make_passing_result() -> GateResult:
    return GateResult(gate1_passed=True, gate2_passed=True, gate3_passed=True, gate4_passed=True)


def test_human_review_record_round_trip_via_to_dict() -> None:
    attempts = tuple(_make_attempt("p.Q.r", i) for i in (1, 2, 3))
    results = tuple(_make_failing_result(i) for i in (1, 2, 3))
    record = HumanReviewRecord(
        node_fqn="p.Q.r",
        attempts=attempts,
        gate_results=results,
        final_gate_errors=results[-1].errors,
    )

    d = record.to_dict()
    # Must be JSON-serializable for receipts.
    encoded = json.dumps(d, default=str)
    decoded = json.loads(encoded)

    assert decoded["node_fqn"] == "p.Q.r"
    assert decoded["reason"] == "max_retries_exhausted"
    assert len(decoded["attempts"]) == 3
    assert len(decoded["gate_results"]) == 3
    assert len(decoded["final_gate_errors"]) == 1
    # Attempt numbers preserved.
    assert [a["attempt_number"] for a in decoded["attempts"]] == [1, 2, 3]


def test_human_review_record_is_frozen() -> None:
    record = HumanReviewRecord(
        node_fqn="a.B.c",
        attempts=(_make_attempt("a.B.c", 1),),
        gate_results=(_make_failing_result(1),),
        final_gate_errors=(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.node_fqn = "mutated"  # type: ignore[misc]


def test_retry_run_report_total_attempts_property() -> None:
    history = tuple(_make_attempt(f"n{i}.X.y", j) for i in range(2) for j in (1, 2, 3))
    report = RetryRunReport(
        successful_attempts=(),
        flagged_for_human_review=(),
        full_attempt_history=history,
    )
    assert report.total_attempts == 6


def test_retry_run_report_success_count_property() -> None:
    successes = (_make_attempt("a.A.a", 1), _make_attempt("b.B.b", 2))
    report = RetryRunReport(
        successful_attempts=successes,
        flagged_for_human_review=(),
        full_attempt_history=successes,
    )
    assert report.success_count == 2
    assert report.review_count == 0


def test_retry_run_report_review_count_property() -> None:
    record = HumanReviewRecord(
        node_fqn="x.Y.z",
        attempts=(_make_attempt("x.Y.z", 1),),
        gate_results=(_make_failing_result(1),),
        final_gate_errors=(),
    )
    report = RetryRunReport(
        successful_attempts=(),
        flagged_for_human_review=(record,),
        full_attempt_history=(_make_attempt("x.Y.z", 1),),
    )
    assert report.review_count == 1
    assert report.success_count == 0


def test_retry_run_report_is_frozen() -> None:
    report = RetryRunReport(
        successful_attempts=(),
        flagged_for_human_review=(),
        full_attempt_history=(),
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        report.successful_attempts = (_make_attempt("a.A.a", 1),)  # type: ignore[misc]


def test_retry_run_report_to_dict_includes_counters() -> None:
    succ = _make_attempt("s.S.s", 1)
    report = RetryRunReport(
        successful_attempts=(succ,),
        flagged_for_human_review=(),
        full_attempt_history=(succ,),
    )
    d = report.to_dict()
    assert d["success_count"] == 1
    assert d["review_count"] == 0
    assert d["total_attempts"] == 1
