"""Literal boundary extraction from call sites (≥2 callers)."""

from __future__ import annotations

import ast

from verify import boundary


def test_integer_literals() -> None:
    t = ast.parse("target(0, 1, -1)", mode="eval")
    assert isinstance(t, ast.Expression)
    c = t.body
    assert isinstance(c, ast.Call)
    out = boundary.extract_literal_args_for_call(c, "target", short_name="target")
    assert out[0] == [0]
    assert out[1] == [1]
    assert out[2] == [-1]


def test_large_integer() -> None:
    t = ast.parse("f(999_999_999_999_999_999_999_999_999_999_9999)", mode="eval")
    c = t.body
    assert isinstance(c, ast.Call)
    out = boundary.extract_literal_args_for_call(c, "f", short_name="f")
    v = out[0][0]
    assert isinstance(v, int) and v > 1 << 50


def test_string_literals() -> None:
    t = ast.parse("f(\"\", ' ', 'longstring')", mode="eval")
    c = t.body
    assert isinstance(c, ast.Call)
    out = boundary.extract_literal_args_for_call(c, "f", short_name="f")
    assert out[0] == [""]
    assert out[1] == [" "]
    assert out[2] == ["longstring"]


def test_none_true_false() -> None:
    t = ast.parse("f(None, True, False)", mode="eval")
    c = t.body
    assert isinstance(c, ast.Call)
    out = boundary.extract_literal_args_for_call(c, "f", short_name="f")
    assert out[0] == [None]
    assert out[1] == [True]
    assert out[2] == [False]


def test_dedupes() -> None:
    merged = boundary.aggregate_boundaries(
        [({0: [0, 0, 0]}, "a"), ({0: [0, 0]}, "b")],
    )
    b = boundary.filter_frequent_literals(merged, min_distinct_callers=2)
    assert 0 in b[0]


def test_at_least_two_callers() -> None:
    """Only when ≥2 distinct callers share a literal (same pos)."""
    merged = boundary.aggregate_boundaries(
        [({0: [42]}, "a"), ({0: [1]}, "b")],  # no value shared
    )
    b = boundary.filter_frequent_literals(merged, min_distinct_callers=2)
    assert 42 not in b.get(0, ())


def test_same_literal_two_callers() -> None:
    merged = boundary.aggregate_boundaries(
        [({0: [7]}, "a"), ({0: [7]}, "b")],
    )
    b = boundary.filter_frequent_literals(merged, min_distinct_callers=2)
    assert 7 in b[0]
