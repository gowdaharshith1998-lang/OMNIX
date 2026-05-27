"""Tests for the D3 property generator (auto-Hypothesis strategies + assertions)."""

from __future__ import annotations

import ast

import pytest

from omnix.dm._types import (
    AnomalyFinding,
    ColumnMapping,
    ColumnSpec,
    PropertySet,
)
from omnix.dm.d3_transformation_synthesis.property_generator import (
    KNOWN_MOJIBAKE,
    KNOWN_SENTINELS,
    MIDNIGHT_UTC_SAMPLES,
    StrategyUnavailable,
    generate_properties,
)


def _col(name="x", raw="INTEGER", norm="INTEGER", nullable=True):
    return ColumnSpec(
        name=name,
        raw_type=raw,
        normalized_type=norm,
        nullable=nullable,
        default=None,
        primary_key=False,
        unique=False,
        comment=None,
    )


def _mapping(legacy="t.x", target="t.x"):
    lt, lc = legacy.split(".")
    tt, tc = target.split(".")
    return ColumnMapping(
        legacy_table=lt,
        legacy_column=lc,
        target_table=tt,
        target_column=tc,
        confidence=0.9,
        status="ok",
    )


def _finding(cat, table="t", col="x", severity="blocker"):
    return AnomalyFinding(
        probe_category=cat,
        legacy_table=table,
        legacy_column=col,
        anomaly_type=f"{cat}_anomaly",
        severity=severity,
        sample_values=(),
        affected_row_count=10,
        remediation_hint="hint",
        requires_human_decision=True,
    )


def test_integer_mapping_emits_type_and_null():
    ps = generate_properties(
        _mapping(),
        (),
        legacy_column=_col(),
        target_column=_col(),
    )
    names = [p.name for p in ps.properties]
    assert "type_preservation" in names
    assert "null_passthrough" in names
    assert ps.coverage_complete


def test_mojibake_blocker_injects_known_samples_into_strategy():
    ps = generate_properties(
        _mapping(),
        (_finding("encoding_anomaly"),),
        legacy_column=_col(norm="STRING"),
        target_column=_col(norm="STRING"),
    )
    survives = [p for p in ps.properties if p.name == "survives_encoding_anomaly"][0]
    assert "KNOWN_MOJIBAKE" in survives.hypothesis_strategy


def test_timezone_drift_emits_preserves_timezone_property():
    ps = generate_properties(
        _mapping(),
        (_finding("timezone_drift"),),
        legacy_column=_col(norm="DATE"),
        target_column=_col(norm="TIMESTAMP_TZ"),
    )
    names = [p.name for p in ps.properties]
    assert "preserves_timezone" in names
    assert "survives_timezone_drift" in names


def test_precision_boundary_emits_precision_clamp():
    ps = generate_properties(
        _mapping(),
        (_finding("precision_boundary"),),
        legacy_column=_col(norm="DECIMAL(10,2)"),
        target_column=_col(norm="DECIMAL(8,2)"),
    )
    names = [p.name for p in ps.properties]
    assert "within_target_precision" in names


def test_sentinel_value_blocker_adds_sentinels():
    ps = generate_properties(
        _mapping(),
        (_finding("sentinel_value"),),
        legacy_column=_col(norm="STRING"),
        target_column=_col(norm="STRING"),
    )
    prop = [p for p in ps.properties if p.name == "survives_sentinel_value"][0]
    assert "KNOWN_SENTINELS" in prop.hypothesis_strategy


def test_not_null_target_emits_no_null_emission():
    ps = generate_properties(
        _mapping(),
        (),
        legacy_column=_col(nullable=False),
        target_column=_col(nullable=False),
    )
    names = [p.name for p in ps.properties]
    assert "no_null_emission" in names


def test_unknown_normalized_type_halts():
    with pytest.raises(StrategyUnavailable):
        generate_properties(
            _mapping(),
            (),
            legacy_column=_col(norm="EXOTIC_VENDOR_TYPE"),
            target_column=_col(norm="STRING"),
        )


def test_lossless_pair_emits_reversibility_property():
    ps = generate_properties(
        _mapping(),
        (),
        legacy_column=_col(norm="VARCHAR(50)"),
        target_column=_col(norm="TEXT"),
    )
    names = [p.name for p in ps.properties]
    assert "reversibility_when_lossless" in names


def test_coverage_complete_true_on_happy_path():
    ps = generate_properties(
        _mapping(),
        (_finding("encoding_anomaly"),),
        legacy_column=_col(norm="STRING"),
        target_column=_col(norm="STRING"),
    )
    assert ps.coverage_complete is True
    assert ps.missing_coverage_reasons == ()


def test_coverage_complete_false_when_blocker_template_missing(monkeypatch):
    # Inject a synthetic blocker category our generator doesn't know about.
    finding = AnomalyFinding(
        probe_category="encoding_anomaly",  # valid Literal — we monkeypatch the map
        legacy_table="t",
        legacy_column="x",
        anomaly_type="exotic",
        severity="blocker",
        sample_values=(),
        affected_row_count=1,
        remediation_hint="h",
        requires_human_decision=True,
    )
    # Remove the entry from the table so the generator must surface missing_reasons.
    from omnix.dm.d3_transformation_synthesis import property_generator

    monkeypatch.setattr(
        property_generator,
        "_BLOCKER_AUGMENTATIONS",
        {},  # empty
    )
    ps = generate_properties(
        _mapping(),
        (finding,),
        legacy_column=_col(norm="STRING"),
        target_column=_col(norm="STRING"),
    )
    assert ps.coverage_complete is False
    assert ps.missing_coverage_reasons


def test_property_assertions_parse_as_python():
    ps = generate_properties(
        _mapping(),
        (_finding("encoding_anomaly"), _finding("sentinel_value")),
        legacy_column=_col(norm="STRING"),
        target_column=_col(norm="STRING"),
    )
    for prop in ps.properties:
        body = f"def _p(v):\n    {prop.assertion}\n"
        ast.parse(body)


def test_strategy_snippets_parse_as_python_expressions():
    ps = generate_properties(
        _mapping(),
        (_finding("encoding_anomaly"),),
        legacy_column=_col(norm="STRING"),
        target_column=_col(norm="STRING"),
    )
    for prop in ps.properties:
        # The strategy must parse as a Python expression in a namespace where
        # ``st`` / ``KNOWN_MOJIBAKE`` etc. are bound — we do a syntactic parse only.
        ast.parse(prop.hypothesis_strategy, mode="eval")


def test_per_blocker_rationale_is_non_empty():
    ps = generate_properties(
        _mapping(),
        (_finding("encoding_anomaly"),),
        legacy_column=_col(norm="STRING"),
        target_column=_col(norm="STRING"),
    )
    for prop in ps.properties:
        assert prop.rationale.strip()


def test_property_set_is_frozen_dataclass():
    ps = generate_properties(
        _mapping(), (), legacy_column=_col(), target_column=_col()
    )
    with pytest.raises(Exception):
        ps.properties = ()  # type: ignore[misc]


def test_blockers_for_other_columns_ignored():
    ps = generate_properties(
        _mapping("t.x", "t.x"),
        (_finding("encoding_anomaly", table="other_table", col="other_col"),),
        legacy_column=_col(norm="STRING"),
        target_column=_col(norm="STRING"),
    )
    names = [p.name for p in ps.properties]
    assert "survives_encoding_anomaly" not in names
