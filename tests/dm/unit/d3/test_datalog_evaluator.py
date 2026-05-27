"""Tests for the pure-Python Datalog evaluator."""

from __future__ import annotations

import pytest

from omnix.dm.d3_transformation_synthesis.datalog import (
    DatalogSyntaxError,
    StratificationError,
    evaluate,
    parse_program,
)


def test_arithmetic_doubling():
    src = "target(X, Y) :- legacy(X, Z), Y == Z * 2."
    edb = {"legacy": {(1, 10), (2, 20)}}
    out = evaluate(src, edb, "target")
    assert set(out) == {(1, 20), (2, 40)}


def test_stratified_negation():
    src = (
        "candidate(X) :- legacy(X).\n"
        "target(X) :- candidate(X), not exclude(X).\n"
    )
    edb = {"legacy": {(1,), (2,), (3,)}, "exclude": {(2,)}}
    out = evaluate(src, edb, "target")
    assert set(out) == {(1,), (3,)}


def test_count_aggregate():
    src = "count_rule(N) :- legacy(X), N = count(X)."
    edb = {"legacy": {(1,), (2,), (3,)}}
    out = evaluate(src, edb, "count_rule")
    assert set(out) == {(3,)}


def test_sum_aggregate():
    src = "total(S) :- legacy(X, V), S = sum(V)."
    edb = {"legacy": {("a", 10), ("b", 20), ("c", 30)}}
    out = evaluate(src, edb, "total")
    assert set(out) == {(60,)}


def test_min_max_aggregate():
    src = (
        "lo(M) :- legacy(X), M = min(X).\n"
        "hi(M) :- legacy(X), M = max(X).\n"
    )
    edb = {"legacy": {(5,), (3,), (9,), (1,)}}
    assert set(evaluate(src, edb, "lo")) == {(1,)}
    assert set(evaluate(src, edb, "hi")) == {(9,)}


def test_negation_cycle_rejected_at_stratification():
    src = (
        "a(X) :- b(X), not a(X).\n"
        "b(1).\n"
    )
    # The body of b/1 isn't an atom; we need a separate edb. Simplify:
    src = (
        "a(X) :- legacy(X), not b(X).\n"
        "b(X) :- legacy(X), not a(X).\n"
    )
    edb = {"legacy": {(1,), (2,)}}
    with pytest.raises(StratificationError):
        evaluate(src, edb, "a")


def test_syntax_error_on_malformed_rule():
    with pytest.raises(DatalogSyntaxError):
        parse_program("target(X) :- legacy(X")


def test_unbound_head_var_rejected_at_parse():
    src = "target(X, Y) :- legacy(X)."
    with pytest.raises(DatalogSyntaxError):
        parse_program(src)


def test_empty_edb_returns_empty_idb():
    src = "target(X) :- legacy(X)."
    out = evaluate(src, {"legacy": set()}, "target")
    assert out == ()


def test_arithmetic_addition():
    src = "target(X, Y) :- legacy(X, Z), Y == Z + 1."
    edb = {"legacy": {(1, 9), (2, 19)}}
    out = evaluate(src, edb, "target")
    assert set(out) == {(1, 10), (2, 20)}


def test_cross_model_relational_to_graph():
    """Convert (parent, child) pairs into a graph adjacency representation."""
    src = (
        "edge(P, C) :- parent_of(P, C).\n"
        "node(N) :- parent_of(N, _C).\n"
        "node(N) :- parent_of(_P, N).\n"
    )
    # Underscore vars aren't supported as anonymous. Rewrite:
    src = (
        "edge(P, C) :- parent_of(P, C).\n"
        "node(N) :- parent_of(N, X).\n"
        "node(N) :- parent_of(X, N).\n"
    )
    edb = {"parent_of": {(1, 2), (2, 3)}}
    edges = set(evaluate(src, edb, "edge"))
    nodes = set(evaluate(src, edb, "node"))
    assert edges == {(1, 2), (2, 3)}
    assert nodes == {(1,), (2,), (3,)}


def test_count_aggregate_over_empty_body():
    src = "total(N) :- legacy(X), N = count(X)."
    edb = {"legacy": set()}
    out = evaluate(src, edb, "total")
    assert set(out) == {(0,)}


def test_timeout_raises():
    """Force a tight deadline by setting timeout_ms=0."""
    src = "target(X) :- legacy(X)."
    edb = {"legacy": {(i,) for i in range(1000)}}
    with pytest.raises(Exception):  # DatalogTimeout
        evaluate(src, edb, "target", timeout_ms=0)


def test_program_is_frozen_dataclass():
    p = parse_program("target(X) :- legacy(X).")
    with pytest.raises(Exception):
        p.rules = ()  # type: ignore[misc]
