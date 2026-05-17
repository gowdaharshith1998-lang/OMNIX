"""Tests for GateResult + GateError contracts."""

from __future__ import annotations

import pytest

from omnix.gates import GateCrashError, GateError, GateResult


def _err(n: int = 1) -> GateError:
    return GateError(gate_number=n, gate_name=f"g{n}", message="boom", details={"k": "v"})


def test_gate_result_passed_property_true_when_all_pass() -> None:
    result = GateResult(
        gate1_passed=True,
        gate2_passed=True,
        gate3_passed=True,
        gate4_passed=True,
    )
    assert result.passed is True
    assert result.errors == ()


def test_gate_result_passed_property_false_when_any_fail() -> None:
    result = GateResult(
        gate1_passed=True,
        gate2_passed=True,
        gate3_passed=False,
        gate4_passed=True,
        gate3_error=_err(3),
    )
    assert result.passed is False


def test_gate_result_errors_collects_only_non_none() -> None:
    e1 = _err(1)
    e4 = _err(4)
    result = GateResult(
        gate1_passed=False,
        gate2_passed=True,
        gate3_passed=True,
        gate4_passed=False,
        gate1_error=e1,
        gate4_error=e4,
    )
    errs = result.errors
    assert errs == (e1, e4)
    assert all(e is not None for e in errs)


def test_gate_error_to_dict_serializes_details() -> None:
    e = GateError(
        gate_number=3,
        gate_name="signature",
        message="mismatch",
        details={"expected": "x", "actual": "y", "normalized_diff": "--- a\n+++ b"},
    )
    d = e.to_dict()
    assert d["gate_number"] == 3
    assert d["gate_name"] == "signature"
    assert d["message"] == "mismatch"
    assert d["details"]["expected"] == "x"
    assert d["details"]["actual"] == "y"
    # to_dict should return a fresh dict (not aliased) so mutations don't leak.
    d["details"]["expected"] = "MUTATED"
    assert e.details["expected"] == "x"


def test_gate_crash_error_attaches_original() -> None:
    original = RuntimeError("jvm died")
    crash = GateCrashError(1, "JAR missing", original=original)
    assert crash.gate_number == 1
    assert crash.original is original
    assert "gate 1 crashed" in str(crash)
    assert "JAR missing" in str(crash)

    # Can also raise/catch as Exception.
    with pytest.raises(GateCrashError) as ei:
        raise crash
    assert ei.value.original is original
