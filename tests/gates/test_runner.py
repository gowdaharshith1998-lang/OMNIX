"""Tests for the gates runner — no-short-circuit semantics + crash handling."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from omnix.gates import GateCrashError, runner
from omnix.orchestrator.attempt import RebuildAttempt
from omnix.spec import DependencyRef, Identity, Signature, Spec, TypeInfo


def _spec(
    canonical: str = "public static String reverse(String)",
    deps: tuple[DependencyRef, ...] = (),
) -> Spec:
    return Spec(
        identity=Identity(
            fqn="com.example.StringUtils.reverse",
            kind="method",
            source_file="StringUtils.java",
            source_line=1,
        ),
        signature=Signature(
            canonical=canonical,
            modifiers=("public", "static"),
            return_type="String",
            param_types=("String",),
        ),
        types=TypeInfo(
            param_types=("java.lang.String",),
            return_type="java.lang.String",
            is_return_primitive=False,
            are_params_primitive=(False,),
        ),
        dependencies=deps,
        target_hints=(),
    )


def _attempt(response: str) -> RebuildAttempt:
    return RebuildAttempt(
        node_fqn="com.example.StringUtils.reverse",
        spec_hash="0" * 64,
        prompt_template_version="v1",
        prompt_text_hash="0" * 64,
        response_text=response,
        timestamp=datetime.now(timezone.utc),
        model="test-model",
    )


def test_runner_runs_all_gates_no_short_circuit() -> None:
    # Gate 1 fails (unbalanced braces), gate 3 fails (wrong signature),
    # gate 4 should still execute.
    bad_source = "class X { public int wrong(int n) { return n;"  # missing close braces
    attempt = _attempt(bad_source)
    spec = _spec()  # expects `public static String reverse(String)`
    result = runner.run(attempt, spec)

    # Gate 1 fails (unbalanced braces).
    assert result.gate1_passed is False
    assert result.gate1_error is not None
    # Gate 3 still ran and fails (signature mismatch).
    assert result.gate3_passed is False
    assert result.gate3_error is not None
    # Multiple errors surfaced — R-6.2 evidence.
    assert len(result.errors) >= 2
    assert result.passed is False


def test_runner_catches_gate_crashes_and_marks_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    def _crashing_check(source_code: str):  # noqa: ANN202
        raise GateCrashError(1, "stub crash", original=RuntimeError("simulated"))

    from omnix.gates import gate1_syntactic

    monkeypatch.setattr(gate1_syntactic, "check", _crashing_check)

    attempt = _attempt("class X { public static String reverse(String s) { return s; } }")
    spec = _spec()
    result = runner.run(attempt, spec)

    assert result.gate1_passed is False
    assert result.gate1_error is not None
    assert "crashed" in result.gate1_error.message
    assert result.gate1_error.details.get("crash") is True
    # Other gates still ran and should pass (valid source, matching spec, no deps).
    assert result.gate2_passed is True
    assert result.gate3_passed is True
    assert result.gate4_passed is True


def test_runner_returns_passed_true_when_all_gates_pass() -> None:
    source = "class StringUtils { public static String reverse(String s) { return s; } }"
    attempt = _attempt(source)
    spec = _spec()
    result = runner.run(attempt, spec)
    assert result.passed is True
    assert result.errors == ()


def test_runner_uses_response_text_when_source_code_none() -> None:
    good_source = "class StringUtils { public static String reverse(String s) { return s; } }"
    attempt = _attempt(good_source)
    spec = _spec()
    # Explicit None -> runner pulls from attempt.response_text.
    result = runner.run(attempt, spec, source_code=None)
    assert result.gate1_passed is True
    assert result.gate3_passed is True


def test_runner_explicit_source_overrides_attempt_response() -> None:
    attempt = _attempt("garbage that would fail everything {{{")
    spec = _spec()
    override = "class StringUtils { public static String reverse(String s) { return s; } }"
    result = runner.run(attempt, spec, source_code=override)
    assert result.gate1_passed is True
    assert result.gate3_passed is True
