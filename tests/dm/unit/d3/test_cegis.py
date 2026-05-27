"""Tests for the Migrator CEGIS layer."""

from __future__ import annotations

import pytest

from omnix.dm._types import (
    AnomalyFinding,
    ColumnMapping,
    ColumnSpec,
    PropertyDef,
    PropertySet,
    ReflexionHalt,
    ReflexionSuccess,
)
from omnix.dm.d3_transformation_synthesis import cegis, llm_synthesizer
from omnix.dm.d3_transformation_synthesis.cegis import (
    SKETCHES,
    run_with_cegis,
    select_sketches,
)


@pytest.fixture(autouse=True)
def _reset_backend():
    llm_synthesizer.set_llm_backend(None)
    yield
    llm_synthesizer.set_llm_backend(None)


def _col(norm="STRING", nullable=True):
    return ColumnSpec(
        name="x",
        raw_type=norm,
        normalized_type=norm,
        nullable=nullable,
        default=None,
        primary_key=False,
        unique=False,
        comment=None,
    )


def _mapping():
    return ColumnMapping(
        legacy_table="t",
        legacy_column="x",
        target_table="t",
        target_column="x",
        confidence=0.95,
        status="ok",
    )


def _finding(cat):
    return AnomalyFinding(
        probe_category=cat,
        legacy_table="t",
        legacy_column="x",
        anomaly_type=cat,
        severity="blocker",
        sample_values=(),
        affected_row_count=1,
        remediation_hint="hint",
        requires_human_decision=True,
    )


def _ps():
    return PropertySet(
        column_mapping_key="t.x",
        properties=(PropertyDef("type_preservation", "st.text()", "pass", None, "type"),),
        coverage_complete=True,
        missing_coverage_reasons=(),
    )


def test_date_to_timestamptz_selects_correct_sketch():
    out = select_sketches(
        _mapping(),
        _col(norm="DATE"),
        _col(norm="TIMESTAMP_TZ"),
        (_finding("timezone_drift"),),
    )
    assert out
    assert out[0].sketch_id == "date_to_timestamptz_utc_midnight"


def test_no_matching_sketch_returns_empty():
    # Unknown bytes-to-bool pair has no sketch.
    out = select_sketches(
        _mapping(),
        _col(norm="BYTES"),
        _col(norm="BOOLEAN"),
        (),
    )
    assert out == ()


def test_pruned_sketches_excluded():
    full = select_sketches(_mapping(), _col(), _col(), ())
    if not full:
        pytest.skip("no sketches matched for STRING→STRING")
    excluded = full[0].sketch_id
    out2 = select_sketches(_mapping(), _col(), _col(), (), pruned_ids=(excluded,))
    assert all(s.sketch_id != excluded for s in out2)


def test_sketches_sorted_by_historical_pass_rate():
    out = select_sketches(_mapping(), _col(), _col(), ())
    rates = [s.historical_pass_rate for s in out]
    assert rates == sorted(rates, reverse=True)


def test_applicable_blocker_overlap_boosts_ranking():
    """A sketch with the matching blocker should rank ahead of one without,
    when they have the same base historical_pass_rate."""
    no_blocker = select_sketches(_mapping(), _col(), _col(), ())
    with_blocker = select_sketches(
        _mapping(), _col(), _col(), (_finding("sentinel_value"),)
    )
    sentinel_idx_no = [
        i for i, s in enumerate(no_blocker) if s.sketch_id == "sentinel_to_none"
    ]
    sentinel_idx_yes = [
        i for i, s in enumerate(with_blocker) if s.sketch_id == "sentinel_to_none"
    ]
    if sentinel_idx_no and sentinel_idx_yes:
        assert sentinel_idx_yes[0] <= sentinel_idx_no[0]


def test_sketches_tuple_is_module_level_immutable():
    assert isinstance(SKETCHES, tuple)
    assert len(SKETCHES) >= 15
    # ensure no duplicate IDs
    ids = [s.sketch_id for s in SKETCHES]
    assert len(set(ids)) == len(ids)


def test_run_with_cegis_returns_success_on_happy_path():
    src = (
        "```python\ndef transform(v):\n    if v is None: return None\n    return v\n```\n"
        "```hypothesis\n# t\n```\n"
    )
    backend, _ = _backend([src])
    llm_synthesizer.set_llm_backend(backend)
    out = run_with_cegis(
        mapping=_mapping(),
        legacy_column=_col(),
        target_column=_col(),
        property_set=_ps(),
        blockers=(),
    )
    assert isinstance(out, ReflexionSuccess)
    assert out.iterations_used == 1


def test_run_with_cegis_records_pruned_sketches_on_halt():
    broken = "```python\ndef transform(v):\n    return 9999\n```\n```hypothesis\n# t\n```"
    backend, _ = _backend([broken])
    llm_synthesizer.set_llm_backend(backend)
    out = run_with_cegis(
        mapping=_mapping(),
        legacy_column=_col(norm="STRING"),
        target_column=_col(norm="STRING"),
        property_set=_ps(),
        blockers=(),
        max_iterations=3,
    )
    # Either an iteration_cap halt or all_sketches_pruned — either way
    # the halt is honest and carries the MFI history.
    assert isinstance(out, ReflexionHalt)
    assert out.halt_reason in ("iteration_cap", "all_sketches_pruned")
    assert len(out.failing_mfis) >= 1


def _backend(responses):
    idx = {"i": 0}

    def _b(s, u, k):
        r = responses[min(idx["i"], len(responses) - 1)]
        idx["i"] += 1
        return llm_synthesizer._BackendResponse(
            text=r, model_id="mock", prompt_tokens=1, completion_tokens=1
        )

    return _b, idx
