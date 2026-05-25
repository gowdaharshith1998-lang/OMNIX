"""Daikon-lite miner tests."""

from __future__ import annotations

from omnix.cloud.verify.daikon_lite import Tracer, compare, mine


def test_mines_non_negative_invariant():
    tr = Tracer()

    @tr.trace("abs_sq")
    def abs_sq(x):
        return x * x

    for x in range(-10, 11):
        abs_sq(x)
    inv = mine(tr)
    exprs = {i.expression for i in inv.union()}
    assert "_ret >= 0" in exprs


def test_mines_constant_invariant():
    tr = Tracer()

    @tr.trace("greet")
    def greet(x):
        return "hi"

    for _ in range(5):
        greet(1)
    inv = mine(tr)
    exprs = {i.expression for i in inv.union()}
    assert "_ret == 'hi'" in exprs


def test_mines_linear_pair():
    tr = Tracer()

    @tr.trace("double")
    def double(x):
        return 2 * x

    for x in range(1, 10):
        double(x)
    inv = mine(tr)
    exprs = {i.expression for i in inv.union()}
    # 2*x relation: ret = 2x + 0
    assert any("== 2.0*x" in e or "== 2*x" in e or "_ret == 2*x" in e or "_ret == 2.0*x" in e
               for e in exprs)


def test_mines_ordering_invariant():
    tr = Tracer()

    @tr.trace("plus_one")
    def plus_one(x):
        return x + 1

    for x in range(0, 10):
        plus_one(x)
    inv = mine(tr)
    exprs = {i.expression for i in inv.union()}
    assert ("x < _ret" in exprs) or ("_ret > x" in exprs)


def test_compare_detects_violated_invariant():
    legacy_tracer = Tracer()
    candidate_tracer = Tracer()

    @legacy_tracer.trace("f")
    def legacy_f(x):
        return x * x  # always >= 0

    @candidate_tracer.trace("f")
    def candidate_f(x):
        return x       # signed -- breaks x*x >= 0 invariant when x<0

    for x in range(-5, 6):
        legacy_f(x)
        candidate_f(x)
    legacy_inv = mine(legacy_tracer)
    cand_inv = mine(candidate_tracer)
    delta = compare(legacy_inv, cand_inv)
    violated = [i.expression for i in delta["violated"]]
    assert "_ret >= 0" in violated


def test_mines_sortedness_on_list_return():
    tr = Tracer()

    @tr.trace("sorted_input")
    def f(arr):
        return sorted(arr)

    for arr in ([3, 1, 2], [1], [9, 8, 7]):
        f(arr)
    inv = mine(tr)
    exprs = {i.expression for i in inv.union()}
    assert "sorted(_ret)" in exprs


def test_compare_returns_three_sets():
    legacy_tr = Tracer()
    cand_tr = Tracer()

    @legacy_tr.trace("id_")
    def id_l(x):
        return x

    @cand_tr.trace("id_")
    def id_c(x):
        return x

    for x in range(1, 6):
        id_l(x)
        id_c(x)
    delta = compare(mine(legacy_tr), mine(cand_tr))
    assert set(delta) == {"violated", "introduced", "agreed"}
    assert delta["violated"] == []
