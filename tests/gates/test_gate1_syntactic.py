"""Tests for gate1_syntactic — pure-Python heuristic + xfail real-parser cases.

Heuristic gap: only catches empty source and unbalanced braces. Real parser
tests stay xfail(strict=True) pending the M1 Phase 5 emitter follow-up,
which teaches the bridge to surface structured ParseProblem fields
(line/column) rather than the raw javac stderr string.
"""

from __future__ import annotations

import pytest

from omnix.gates import gate1_syntactic

# ----- Heuristic (pure-Python) path ----------------------------------------


def test_empty_source_returns_gate_error_with_empty_source_reason() -> None:
    err = gate1_syntactic.check("")
    assert err is not None
    assert err.gate_number == 1
    assert err.gate_name == "syntactic"
    assert err.details["reason"] == "empty_source"


def test_whitespace_only_source_returns_gate_error_with_empty_source_reason() -> None:
    err = gate1_syntactic.check("   \n  \t  \n")
    assert err is not None
    assert err.details["reason"] == "empty_source"


def test_balanced_braces_returns_none() -> None:
    src = "class Foo { void x() {} }"
    err = gate1_syntactic.check(src)
    assert err is None


def test_unbalanced_opens_returns_gate_error() -> None:
    src = "class Foo { void x() {"
    err = gate1_syntactic.check(src)
    assert err is not None
    assert err.details["reason"] == "unbalanced_braces"
    assert err.details["open"] == 2
    assert err.details["close"] == 0


def test_unbalanced_closes_returns_gate_error() -> None:
    src = "} }"
    err = gate1_syntactic.check(src)
    assert err is not None
    assert err.details["reason"] == "unbalanced_braces"
    assert err.details["open"] == 0
    assert err.details["close"] == 2


def test_unbalanced_one_off_returns_gate_error() -> None:
    src = "class Foo { void x() {} "  # missing closing class brace
    err = gate1_syntactic.check(src)
    assert err is not None
    assert err.details["reason"] == "unbalanced_braces"


def test_balanced_with_nested_braces_returns_none() -> None:
    src = """
    class Foo {
        void x() {
            if (true) {
                while (false) {
                    {}
                }
            }
        }
    }
    """
    err = gate1_syntactic.check(src)
    assert err is None


def test_returns_gate_error_dataclass_with_correct_gate_metadata() -> None:
    err = gate1_syntactic.check("{")
    assert err is not None
    assert err.gate_number == 1
    assert err.gate_name == "syntactic"
    assert isinstance(err.details, dict)


# ----- Real-parser xfail cases ---------------------------------------------


def test_real_parser_catches_syntax_error_in_method_body() -> None:
    # Braces balance, so the heuristic passes — only real parse catches the
    # missing semicolon.
    src = """
    class Foo {
        void x() {
            int y = 1
        }
    }
    """
    err = gate1_syntactic.check(src)
    assert err is not None
    assert err.gate_number == 1


@pytest.mark.xfail(
    strict=True,
    reason="M1 Phase 5 (emitter follow-up): JAR vendored + bridge real, but "
    "parser.py emits the raw javac stderr without extracting ParseProblem "
    "line/col into structured fields. Gate1 receives the message but "
    "details['line']/details['column'] stay None. Flipped when the M1-finisher "
    "Phase 5 emitter slice surfaces structured ParseProblem fields.",
)
def test_real_parser_reports_line_column_for_error() -> None:
    src = "class Foo { void x() { int y = ; } }"
    err = gate1_syntactic.check(src)
    assert err is not None
    assert err.details.get("line") is not None
    assert err.details.get("column") is not None


@pytest.mark.xfail(
    strict=True,
    reason="M1 Phase 5 (test-rewrite housekeeping): Test source is itself "
    "unbalanced (3 opens / 1 close) — both the heuristic AND the real parser "
    "reject it. Test premise was wrong; rewriting with valid sealed/record "
    "Java 21 source ships alongside the M1 Phase 5 emitter follow-up. "
    "Marker kept as a tripwire so the rewrite isn't forgotten.",
)
def test_real_parser_succeeds_on_valid_java21_source_with_invalid_brace_count() -> None:
    # Source is intentionally minimal — see xfail reason. Real parser also
    # rejects this exact text because it's genuinely truncated.
    src = """
    public class Foo {
        public sealed interface Shape permits Circle, Square {
        public record Circle(double r) implements Shape {}
    """
    err = gate1_syntactic.check(src)
    assert err is None
