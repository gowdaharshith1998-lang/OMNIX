"""Tests for gate6_equivalence harness orchestration."""

from __future__ import annotations

from pathlib import Path

from omnix.gates.gate6_equivalence import ProbeResult, run_harness


def _reverse_source() -> str:
    return """
    package com.example;

    public class StringUtils {
        public static String reverse(String value) {
            return value == null ? null : new StringBuilder(value).reverse().toString();
        }
    }
    """


def test_stringutils_reverse_identity_pair_emits_matching_probe_results() -> None:
    probes = [[""], [" "], ["a"], ["hello"]]

    results = run_harness(
        _reverse_source(),
        _reverse_source(),
        "com.example.StringUtils",
        "reverse",
        probes,
        parameter_types=["java.lang.String"],
    )

    assert len(results) == 4
    assert all(isinstance(r, ProbeResult) for r in results)
    for result in results:
        assert result.input in probes
        assert result.return_value_legacy == result.return_value_rebuilt
        assert result.exception_legacy is None
        assert result.exception_rebuilt is None
        assert result.stdout_legacy_sha256 == result.stdout_rebuilt_sha256
        assert result.stderr_legacy_sha256 == result.stderr_rebuilt_sha256
        assert result.wall_clock_bucket_legacy != "timeout"
        assert result.wall_clock_bucket_rebuilt != "timeout"


def test_probe_runner_captures_system_exit_without_stopping_next_probe() -> None:
    legacy = """
    package com.example;
    public class ExitUtils {
        public static String maybeExit(String value) {
            if ("exit".equals(value)) System.exit(7);
            return value;
        }
    }
    """
    rebuilt = """
    package com.example;
    public class ExitUtils {
        public static String maybeExit(String value) {
            return value;
        }
    }
    """

    results = run_harness(
        legacy,
        rebuilt,
        "com.example.ExitUtils",
        "maybeExit",
        [["exit"], ["ok"]],
        parameter_types=["java.lang.String"],
    )

    assert len(results) == 2
    assert results[0].legacy_outcome == "runtime_crash"
    assert "exit 7" in (results[0].exception_legacy or "")
    assert results[0].rebuilt_outcome == "returned"
    assert results[1].legacy_outcome == "returned"
    assert results[1].return_value_legacy == "ok"


def test_deterministic_probe_repeats_same_legacy_observations() -> None:
    first = run_harness(
        _reverse_source(),
        _reverse_source(),
        "com.example.StringUtils",
        "reverse",
        [["stable"]],
        parameter_types=["java.lang.String"],
    )[0]
    second = run_harness(
        _reverse_source(),
        _reverse_source(),
        "com.example.StringUtils",
        "reverse",
        [["stable"]],
        parameter_types=["java.lang.String"],
    )[0]

    assert first.legacy_outcome == second.legacy_outcome
    assert first.return_value_legacy == second.return_value_legacy
    assert first.exception_legacy == second.exception_legacy
    assert first.stdout_legacy_sha256 == second.stdout_legacy_sha256
    assert first.stderr_legacy_sha256 == second.stderr_legacy_sha256


def test_probe_timeout_marks_only_that_side() -> None:
    legacy = """
    package com.example;
    public class SlowUtils {
        public static String maybeSlow(String value) throws Exception {
            if ("slow".equals(value)) Thread.sleep(2000);
            return value;
        }
    }
    """
    rebuilt = legacy

    results = run_harness(
        legacy,
        rebuilt,
        "com.example.SlowUtils",
        "maybeSlow",
        [["slow"]],
        parameter_types=["java.lang.String"],
        timeout_s=0.2,
    )

    assert len(results) == 1
    assert results[0].wall_clock_bucket_legacy == "timeout"
    assert results[0].wall_clock_bucket_rebuilt == "timeout"
    assert results[0].legacy_outcome == "timeout"
    assert results[0].rebuilt_outcome == "timeout"


def test_probe_runner_jar_is_declared_for_vendor_integrity() -> None:
    vendor_dir = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "omnix"
        / "semantic"
        / "java"
        / "vendor"
    )

    assert (vendor_dir / "equivalence-probe-runner.jar").exists()
