"""Tests for the D2 active-inference probe planner (P5)."""

from __future__ import annotations

from omnix.dm._types import ColumnMapping, SchemaSpec, TableSpec
from omnix.dm.d2_edge_case_profiling.probe_planner import (
    PROBE_CATEGORIES,
    plan,
)


def _mapping(name="email", status="ok", confidence=0.92):
    return ColumnMapping(
        legacy_table="owner",
        legacy_column=name,
        target_table="owner",
        target_column=name,
        confidence=confidence,
        status=status,
        candidates=(),
        rationale="",
    )


_EMPTY_SCHEMA = SchemaSpec(dialect="postgres", name="default", tables=())


def test_no_mapping_silently_dropped():
    mappings = (
        _mapping("a", "ok", 0.99),
        _mapping("b", "low_confidence", 0.7),
        _mapping("c", "ambiguous", 0.72),
        _mapping("d", "no_match", 0.0),
    )
    p = plan(mappings, _EMPTY_SCHEMA)
    probed_pairs = {(r.legacy_table, r.legacy_column) for r in p.requests}
    excluded_pairs = {(t, c) for (t, c, _) in p.excluded}
    # Every mapping appears in either probed or excluded
    for m in mappings:
        pair = (m.legacy_table, m.legacy_column)
        assert pair in probed_pairs or pair in excluded_pairs


def test_no_match_is_excluded_explicitly():
    mappings = (_mapping("ghost", "no_match", 0.0),)
    p = plan(mappings, _EMPTY_SCHEMA)
    assert any(
        col == "ghost" and ("no_match" in reason or "nothing to probe" in reason)
        for (tbl, col, reason) in p.excluded
    )
    # And no probe was scheduled for this mapping
    assert not any(r.legacy_column == "ghost" for r in p.requests)


def test_low_confidence_gets_higher_priority():
    mappings = (
        _mapping("ok_col", "ok", 0.95),
        _mapping("uncertain", "low_confidence", 0.65),
    )
    p = plan(mappings, _EMPTY_SCHEMA, max_total_cost_ms=99_999)
    # Among scheduled requests, the average priority for the uncertain column
    # should be higher than for the ok column.
    ok_priorities = [r.priority for r in p.requests if r.legacy_column == "ok_col"]
    unc_priorities = [r.priority for r in p.requests if r.legacy_column == "uncertain"]
    assert ok_priorities
    assert unc_priorities
    assert sum(unc_priorities) / len(unc_priorities) > sum(ok_priorities) / len(ok_priorities)


def test_budget_enforced():
    mappings = tuple(
        _mapping(f"col_{i}", "low_confidence", 0.7) for i in range(10)
    )
    # tight budget — only a handful should fit
    p = plan(mappings, _EMPTY_SCHEMA, max_total_cost_ms=2_000)
    assert p.total_estimated_cost_ms <= 2_000
    # Some probes must have been deferred
    assert any("deferred" in reason for (_, _, reason) in p.excluded)


def test_determinism_with_seed():
    mappings = (
        _mapping("a", "low_confidence", 0.7),
        _mapping("b", "ok", 0.9),
        _mapping("c", "ambiguous", 0.71),
    )
    p1 = plan(mappings, _EMPTY_SCHEMA, seed=42)
    p2 = plan(mappings, _EMPTY_SCHEMA, seed=42)
    assert p1.requests == p2.requests
    assert p1.efe_trace == p2.efe_trace


def test_six_probe_categories_per_mapping():
    """Each non-no-match mapping should generate 6 candidate probes (subject
    to budget)."""
    mappings = (_mapping("x", "low_confidence", 0.7),)
    p = plan(mappings, _EMPTY_SCHEMA, max_total_cost_ms=99_999)
    cats = {r.category for r in p.requests}
    assert cats == set(PROBE_CATEGORIES)
