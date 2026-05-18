"""Tests for gate5_property — Hypothesis-driven Java equivalence."""

from __future__ import annotations

from pathlib import Path

import pytest
from hypothesis import strategies as st

from omnix.gates import gate5_property
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


def _string_utils_reverse_source(body: str) -> str:
    return f"""
    package com.example;

    public class StringUtils {{
        public static String reverse(String str) {{
            {body}
        }}
    }}
    """


def test_identical_string_reverse_sources_pass_with_many_examples(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNIX_GATE5_MAX_EXAMPLES", "100")
    source = _string_utils_reverse_source(
        "return str == null ? null : new StringBuilder(str).reverse().toString();"
    )

    err = gate5_property.check(source, source, _node())

    assert err is None


def test_broken_string_reverse_reports_shrunk_diverging_input(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNIX_GATE5_MAX_EXAMPLES", "40")
    legacy = _string_utils_reverse_source(
        "return str == null ? null : new StringBuilder(str).reverse().toString();"
    )
    rebuilt = _string_utils_reverse_source("return str.substring(1);")

    err = gate5_property.check(legacy, rebuilt, _node())

    assert err is not None
    assert err.gate_number == 5
    assert err.gate_name == "property_based"
    assert err.details["status"] == "failed"
    assert "diverging_input" in err.details
    diverging = err.details["diverging_input"][0]
    assert isinstance(diverging, str)
    assert len(diverging) <= 2


def test_symmetric_java_exceptions_are_equivalent(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIX_GATE5_MAX_EXAMPLES", "30")
    source = """
    package com.example;

    public class ThrowingUtils {
        public static int parseInt(String value) {
            return Integer.parseInt(value);
        }
    }
    """

    err = gate5_property.check(
        source,
        source,
        _node(
            fqn="com.example.ThrowingUtils.parseInt",
            params=("java.lang.String",),
            return_type="int",
        ),
    )

    assert err is None


def test_asymmetric_java_exception_is_a_divergence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIX_GATE5_MAX_EXAMPLES", "30")
    legacy = """
    package com.example;

    public class ThrowingUtils {
        public static int parseInt(String value) {
            return Integer.parseInt(value);
        }
    }
    """
    rebuilt = """
    package com.example;

    public class ThrowingUtils {
        public static int parseInt(String value) {
            try {
                return Integer.parseInt(value);
            } catch (NumberFormatException ex) {
                return 0;
            }
        }
    }
    """

    err = gate5_property.check(
        legacy,
        rebuilt,
        _node(
            fqn="com.example.ThrowingUtils.parseInt",
            params=("java.lang.String",),
            return_type="int",
        ),
    )

    assert err is not None
    assert err.details["status"] == "failed"
    assert err.details["reason"] == "behavior_divergence"
    assert err.details["legacy_exception"] == "java.lang.NumberFormatException"
    assert err.details["rebuilt_exception"] is None


def test_unknown_parameter_type_is_skipped() -> None:
    source = """
    package com.example;
    public class CustomUtils {
        public static int count(Custom value) { return 0; }
    }
    class Custom {}
    """

    err = gate5_property.check(
        source,
        source,
        _node(
            fqn="com.example.CustomUtils.count",
            params=("com.example.Custom",),
            return_type="int",
        ),
    )

    assert err is not None
    assert err.details["status"] == "skipped"
    assert err.details["reason"] == "unsupported_parameter_type"
    assert err.details["unsupported_types"] == ["com.example.Custom"]


def test_high_strategy_rejection_is_inconclusive(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("OMNIX_GATE5_MAX_EXAMPLES", "25")
    monkeypatch.setitem(
        gate5_property.JAVA_TYPE_STRATEGIES,
        "java.lang.String",
        st.text().filter(lambda _value: False),
    )
    source = _string_utils_reverse_source("return str;")

    err = gate5_property.check(source, source, _node())

    assert err is not None
    assert err.details["status"] == "inconclusive"
    assert err.details["reason"] == "high_assume_rejection_rate"
    assert err.details["examples_tried"] >= err.details["examples_used"]


def test_harness_jar_is_declared_for_vendor_integrity() -> None:
    vendor_dir = (
        Path(__file__).resolve().parent.parent.parent
        / "src"
        / "omnix"
        / "semantic"
        / "java"
        / "vendor"
    )

    assert (vendor_dir / "java-equivalence-harness.jar").exists()
