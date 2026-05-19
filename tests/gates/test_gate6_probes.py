"""Tests for Gate 6 probe generation."""

from __future__ import annotations

from omnix.gates.gate6_equivalence import (
    DEFAULT_CONSTRUCT_MARKER,
    FLOAT_MARKER,
    ProbeSet,
    generate_probe_set,
    generate_probes,
    run_harness,
)
from omnix.gates.result import GateError
from omnix.semantic.node import SemanticNode, SourceLocation


def _node(
    *,
    fqn: str = "com.example.StringUtils.reverse",
    params: tuple[str, ...] = ("java.lang.String",),
    return_type: str | None = "java.lang.String",
) -> SemanticNode:
    return SemanticNode(
        fqn=fqn,
        kind="method",
        signature="public static java.lang.String reverse(java.lang.String)",
        resolved_param_types=params,
        resolved_return_type=return_type,
        dependency_edges=(),
        source_location=SourceLocation(file_path="StringUtils.java", line=1),
    )


def test_generate_probes_includes_string_boundaries_and_requested_random_count() -> None:
    probes = generate_probes(_node(), num_random=100)

    assert [None] in probes
    assert [""] in probes
    assert [" "] in probes
    assert ["a"] in probes
    assert ["A" * 1000] in probes
    assert ["\U0001f984"] in probes
    assert len(probes) >= 106


def test_generate_probe_set_reports_details_and_counterexample_injection() -> None:
    gate5_error = GateError(
        gate_number=5,
        gate_name="property_based",
        message="property-based equivalence divergence",
        details={
            "status": "failed",
            "reason": "behavior_divergence",
            "diverging_input": ["ab"],
        },
    )

    probe_set = generate_probe_set(_node(), num_random=0, gate5_error=gate5_error)

    assert isinstance(probe_set, ProbeSet)
    assert ["ab"] in probe_set.probes
    assert probe_set.details["boundary_count"] == 6
    assert probe_set.details["random_count"] == 0
    assert probe_set.details["injected_count"] == 1
    assert probe_set.details["probe_count"] == len(probe_set.probes)


def test_generate_probes_never_exceeds_wall_clock_cap() -> None:
    probes = generate_probes(_node(), num_random=250)

    assert len(probes) == 200


def test_unknown_type_probe_set_is_partial_and_includes_null_plus_default_marker() -> None:
    probe_set = generate_probe_set(
        _node(
            fqn="com.example.CustomUtils.value",
            params=("com.example.Custom",),
            return_type="int",
        ),
        num_random=10,
    )

    assert [None] in probe_set.probes
    assert [{DEFAULT_CONSTRUCT_MARKER: "com.example.Custom"}] in probe_set.probes
    assert probe_set.details["partial"] is True
    assert probe_set.details["partial_types"] == ["com.example.Custom"]
    assert probe_set.details["random_count"] == 0


def test_double_special_float_markers_run_through_gate6_harness() -> None:
    source = """
    package com.example;

    public class MathUtils {
        public static double identity(double value) {
            return value;
        }
    }
    """
    probes = [
        [{FLOAT_MARKER: "NaN"}],
        [{FLOAT_MARKER: "+Infinity"}],
        [{FLOAT_MARKER: "-Infinity"}],
        [0.0],
    ]

    results = run_harness(
        source,
        source,
        "com.example.MathUtils",
        "identity",
        probes,
        parameter_types=["double"],
    )

    assert [r.return_value_legacy for r in results] == [
        {FLOAT_MARKER: "NaN"},
        {FLOAT_MARKER: "+Infinity"},
        {FLOAT_MARKER: "-Infinity"},
        0.0,
    ]
    assert [r.return_value_rebuilt for r in results] == [
        {FLOAT_MARKER: "NaN"},
        {FLOAT_MARKER: "+Infinity"},
        {FLOAT_MARKER: "-Infinity"},
        0.0,
    ]


def test_default_construct_marker_runs_through_gate6_harness() -> None:
    source = """
    package com.example;

    public class CustomUtils {
        public static int value(Custom value) {
            return value == null ? -1 : value.value;
        }
    }

    class Custom {
        int value;
        Custom() {
            value = 42;
        }
    }
    """
    probe_set = generate_probe_set(
        _node(
            fqn="com.example.CustomUtils.value",
            params=("com.example.Custom",),
            return_type="int",
        ),
        num_random=0,
    )

    results = run_harness(
        source,
        source,
        "com.example.CustomUtils",
        "value",
        probe_set.probes,
        parameter_types=["com.example.Custom"],
    )

    assert [r.return_value_legacy for r in results] == [-1, 42]
    assert [r.return_value_rebuilt for r in results] == [-1, 42]
