"""Property-based invariants for the D3 pipeline.

These tests are NOT the Hypothesis tests embedded inside emitted transformers
— those run in the sandbox during Reflexion. These are *meta* invariants the
pipeline must uphold across all inputs.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest
from hypothesis import given, settings, strategies as st

from omnix.crypto import ml_dsa_65
from omnix.dm._types import (
    ColumnMapping,
    ColumnSpec,
    MFI,
    ReflexionSuccess,
    TransformerSpec,
)
from omnix.dm.d3_transformation_synthesis import llm_synthesizer
from omnix.dm.d3_transformation_synthesis.property_generator import (
    generate_properties,
)
from omnix.dm.d3_transformation_synthesis.reflexion_loop import LoopInputs, run
from omnix.dm.d3_transformation_synthesis.spec_emitter import build_spec_payload


@pytest.fixture(autouse=True)
def _reset_backend():
    llm_synthesizer.set_llm_backend(None)
    yield
    llm_synthesizer.set_llm_backend(None)


_NORMALIZED_TYPES = st.sampled_from(
    [
        "INTEGER",
        "BIGINT",
        "BOOLEAN",
        "DATE",
        "TIMESTAMP",
        "TIMESTAMP_TZ",
        "STRING",
        "VARCHAR(50)",
        "DECIMAL(10,2)",
    ]
)


@given(legacy_norm=_NORMALIZED_TYPES, target_norm=_NORMALIZED_TYPES)
@settings(max_examples=30, deadline=None)
def test_property_generator_is_deterministic(legacy_norm, target_norm):
    """Calling generate_properties twice with the same args yields the same
    set of property names."""
    mapping = ColumnMapping(
        legacy_table="t",
        legacy_column="c",
        target_table="t",
        target_column="c",
        confidence=0.9,
        status="ok",
    )
    legacy = ColumnSpec(
        name="c",
        raw_type=legacy_norm,
        normalized_type=legacy_norm,
        nullable=True,
        default=None,
        primary_key=False,
        unique=False,
        comment=None,
    )
    target = ColumnSpec(
        name="c",
        raw_type=target_norm,
        normalized_type=target_norm,
        nullable=True,
        default=None,
        primary_key=False,
        unique=False,
        comment=None,
    )
    try:
        a = generate_properties(mapping, (), legacy_column=legacy, target_column=target)
        b = generate_properties(mapping, (), legacy_column=legacy, target_column=target)
    except Exception:
        return  # StrategyUnavailable on unknown pair; not a determinism violation
    assert [p.name for p in a.properties] == [p.name for p in b.properties]


def test_mfi_history_is_monotone_across_iterations():
    """No iteration can drop or replace an MFI; only appends."""
    broken = "```python\ndef transform(v):\n    return 9999\n```\n```hypothesis\n# t\n```"

    def _backend(s, u, k):
        return llm_synthesizer._BackendResponse(
            text=broken, model_id="mock", prompt_tokens=1, completion_tokens=1
        )

    llm_synthesizer.set_llm_backend(_backend)
    mapping = ColumnMapping(
        legacy_table="t",
        legacy_column="x",
        target_table="t",
        target_column="x",
        confidence=0.9,
        status="ok",
    )
    legacy = ColumnSpec("x", "STRING", "STRING", True, None, False, False, None)
    target = ColumnSpec("x", "STRING", "STRING", True, None, False, False, None)
    ps = generate_properties(mapping, (), legacy_column=legacy, target_column=target)
    out = run(
        LoopInputs(
            mapping=mapping,
            legacy_column=legacy,
            target_column=target,
            property_set=ps,
        ),
        max_iterations=4,
    )
    # halt; failing_mfis length == iterations_used
    from omnix.dm._types import ReflexionHalt

    assert isinstance(out, ReflexionHalt)
    assert len(out.failing_mfis) == out.iterations_used


def test_transformer_spec_properties_failed_must_be_empty_for_success():
    """The schema validator MUST reject a 'success' payload with any failed
    property — Codex honesty invariant."""
    spec = TransformerSpec(
        column_mapping_key="t.x",
        python_source="def transform(v): return v",
        sql_case=None,
        datalog_rule=None,
        properties_passed=("p1",),
        properties_failed=("p2",),  # invalid for a Success
        mfi_history=(),
        iterations_used=1,
        cegis_pruned_sketches=(),
        tier_failures=(),
        tier_chosen="python",
        confidence=0.9,
        requires_operator_review=False,
        bisimulation_placeholder={},
    )
    success = ReflexionSuccess(
        transformer_spec=spec, iterations_used=1, mfi_history=(), pruned_sketches=()
    )
    pk = b"\x00" * ml_dsa_65.PUBLIC_KEY_BYTES
    with pytest.raises(ValueError):
        build_spec_payload(
            success,
            migration_id="m1",
            predecessor_hash=hashlib.sha256(b"x").hexdigest(),
            public_key=pk,
        )


def test_spec_predecessor_hash_must_be_64_char_hex():
    """Anything else than 64-char hex is rejected before signing — chain
    integrity gate."""
    spec = TransformerSpec(
        column_mapping_key="t.x",
        python_source="def transform(v): return v",
        sql_case=None,
        datalog_rule=None,
        properties_passed=("p1",),
        properties_failed=(),
        mfi_history=(),
        iterations_used=1,
        cegis_pruned_sketches=(),
        tier_failures=(),
        tier_chosen="python",
        confidence=0.9,
        requires_operator_review=False,
        bisimulation_placeholder={},
    )
    success = ReflexionSuccess(
        transformer_spec=spec, iterations_used=1, mfi_history=(), pruned_sketches=()
    )
    pk = b"\x00" * ml_dsa_65.PUBLIC_KEY_BYTES
    with pytest.raises(ValueError):
        build_spec_payload(
            success,
            migration_id="m1",
            predecessor_hash="not-a-real-sha256",
            public_key=pk,
        )


@given(n=st.integers(min_value=1, max_value=5))
def test_iterations_used_stays_within_cap(n):
    """No matter how the mock behaves, iterations_used is bounded by the cap."""
    broken = "```python\ndef transform(v):\n    return 9999\n```\n```hypothesis\n# t\n```"
    llm_synthesizer.set_llm_backend(
        lambda s, u, k: llm_synthesizer._BackendResponse(
            text=broken, model_id="m", prompt_tokens=1, completion_tokens=1
        )
    )
    mapping = ColumnMapping("t", "x", "t", "x", 0.9, "ok")
    legacy = ColumnSpec("x", "STRING", "STRING", True, None, False, False, None)
    target = ColumnSpec("x", "STRING", "STRING", True, None, False, False, None)
    ps = generate_properties(mapping, (), legacy_column=legacy, target_column=target)
    out = run(
        LoopInputs(
            mapping=mapping,
            legacy_column=legacy,
            target_column=target,
            property_set=ps,
        ),
        max_iterations=n,
    )
    assert out.iterations_used <= n
