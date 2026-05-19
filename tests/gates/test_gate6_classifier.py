"""Tests for Gate 6 result classification."""

from __future__ import annotations

from omnix.gates.gate6_equivalence import (
    ClassifiedProbe,
    ProbeResult,
    classify_results,
    evaluate_results,
)

EMPTY_SHA = "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
ALT_SHA = "0" * 64
OTHER_SHA = "1" * 64


def _result(
    *,
    input_value: list[object] | None = None,
    legacy_outcome: str = "returned",
    rebuilt_outcome: str = "returned",
    wall_clock_bucket_legacy: str = "<10ms",
    wall_clock_bucket_rebuilt: str = "<10ms",
    stdout_legacy_sha256: str = EMPTY_SHA,
    stdout_rebuilt_sha256: str = EMPTY_SHA,
    stderr_legacy_sha256: str = EMPTY_SHA,
    stderr_rebuilt_sha256: str = EMPTY_SHA,
    return_value_legacy: object = "same",
    return_value_rebuilt: object = "same",
    exception_legacy: str | None = None,
    exception_rebuilt: str | None = None,
) -> ProbeResult:
    return ProbeResult(
        input=[] if input_value is None else input_value,
        legacy_outcome=legacy_outcome,
        rebuilt_outcome=rebuilt_outcome,
        wall_clock_bucket_legacy=wall_clock_bucket_legacy,
        wall_clock_bucket_rebuilt=wall_clock_bucket_rebuilt,
        stdout_legacy_sha256=stdout_legacy_sha256,
        stdout_rebuilt_sha256=stdout_rebuilt_sha256,
        stderr_legacy_sha256=stderr_legacy_sha256,
        stderr_rebuilt_sha256=stderr_rebuilt_sha256,
        return_value_legacy=return_value_legacy,
        return_value_rebuilt=return_value_rebuilt,
        exception_legacy=exception_legacy,
        exception_rebuilt=exception_rebuilt,
    )


def test_classify_results_assigns_exactly_one_bucket_per_probe() -> None:
    probes = [
        _result(),
        _result(return_value_rebuilt="different"),
        _result(exception_legacy="java.lang.IllegalArgumentException"),
        _result(stdout_legacy_sha256=ALT_SHA, stdout_rebuilt_sha256=EMPTY_SHA),
        _result(
            stdout_legacy_sha256=ALT_SHA,
            stdout_rebuilt_sha256=EMPTY_SHA,
            input_value=["random"],
        ),
        _result(wall_clock_bucket_legacy="<1ms", wall_clock_bucket_rebuilt="<1s"),
        _result(return_value_legacy=1e8, return_value_rebuilt=1e8 + 1e-8),
    ]

    classified = classify_results(
        probes,
        legacy_replay=lambda result: [
            _result(input_value=result.input, stdout_legacy_sha256=ALT_SHA),
            _result(input_value=result.input, stdout_legacy_sha256=OTHER_SHA),
            _result(input_value=result.input, stdout_legacy_sha256=ALT_SHA),
        ]
        if result.input == ["random"]
        else [],
    )

    assert all(isinstance(item, ClassifiedProbe) for item in classified)
    assert [item.classification for item in classified] == [
        "equivalent",
        "value_diverge",
        "exception_diverge",
        "stdout_diverge_deterministic",
        "stdout_diverge_stochastic",
        "wall_clock_diverge",
        "fp_tolerance_diverge",
    ]


def test_real_bug_classifications_fail_gate6_overall() -> None:
    evaluation = evaluate_results(
        [
            _result(input_value=["x"], return_value_legacy="x", return_value_rebuilt="y"),
            _result(input_value=["ok"]),
        ]
    )

    assert evaluation.status == "failed"
    assert evaluation.error is not None
    assert evaluation.details["divergence_count"] == 1
    assert evaluation.details["diverging_input"] == ["x"]
    assert evaluation.details["classification"] == "value_diverge"


def test_stochastic_return_value_is_accepted_with_note_after_replay() -> None:
    probe = _result(
        input_value=["random"],
        return_value_legacy="Hi",
        return_value_rebuilt="Hey",
    )

    classified = classify_results(
        [probe],
        legacy_replay=lambda result: [
            _result(input_value=result.input, return_value_legacy="Hi"),
            _result(input_value=result.input, return_value_legacy="Hey"),
            _result(input_value=result.input, return_value_legacy="Hi"),
        ],
    )

    assert classified[0].classification == "stdout_diverge_stochastic"


def test_small_probe_set_is_inconclusive_without_real_divergence() -> None:
    evaluation = evaluate_results([_result()])

    assert evaluation.status == "inconclusive"
    assert evaluation.error is not None
    assert evaluation.details["probe_count"] == 1
    assert evaluation.details["reason"] == "insufficient_probe_count"


def test_fp_tolerance_counts_as_accepted_note_not_failure() -> None:
    probes = [
        _result(return_value_legacy=1e8, return_value_rebuilt=1e8 + 1e-8)
        for _ in range(20)
    ]

    evaluation = evaluate_results(probes)

    assert evaluation.status == "passed"
    assert evaluation.error is None
    assert evaluation.details["divergence_count"] == 0
    assert evaluation.details["accepted_with_note_count"] == 20


def test_passed_gate6_details_include_probe_counts() -> None:
    evaluation = evaluate_results([_result(input_value=[i]) for i in range(20)])

    assert evaluation.status == "passed"
    assert evaluation.details["probe_count"] == 20
    assert evaluation.details["divergence_count"] == 0
    assert evaluation.details["accepted_with_note_count"] == 0
