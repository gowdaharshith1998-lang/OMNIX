"""Tests for the Datalog tier emitter."""

from __future__ import annotations

import pytest

from omnix.dm._types import ColumnMapping, TierFailure
from omnix.dm.d3_transformation_synthesis import llm_synthesizer
from omnix.dm.d3_transformation_synthesis.datalog_tier import (
    emit_datalog_rule,
    verify_datalog_against_python,
)


@pytest.fixture(autouse=True)
def _reset_backend():
    llm_synthesizer.set_llm_backend(None)
    yield
    llm_synthesizer.set_llm_backend(None)


def _mapping():
    return ColumnMapping(
        legacy_table="legacy",
        legacy_column="value",
        target_table="target",
        target_column="value",
        confidence=0.95,
        status="ok",
    )


def test_passthrough_rule_parses():
    rule = "```datalog\ntarget(X, Y) :- legacy(X, Y).\n```"
    llm_synthesizer.set_llm_backend(
        lambda s, u, k: llm_synthesizer._BackendResponse(text=rule, model_id="x")
    )
    out = emit_datalog_rule(
        python_source="def transform(v): return v",
        mapping=_mapping(),
    )
    assert isinstance(out, str)
    assert "target" in out


def test_arithmetic_rule_parses():
    rule = "```datalog\ntarget(X, Y) :- legacy(X, Z), Y == Z * 2.\n```"
    llm_synthesizer.set_llm_backend(
        lambda s, u, k: llm_synthesizer._BackendResponse(text=rule, model_id="x")
    )
    out = emit_datalog_rule(
        python_source="def transform(v): return v * 2",
        mapping=_mapping(),
    )
    assert isinstance(out, str)
    assert "Z * 2" in out


def test_missing_datalog_block_returns_failure():
    llm_synthesizer.set_llm_backend(
        lambda s, u, k: llm_synthesizer._BackendResponse(text="no fence", model_id="x")
    )
    out = emit_datalog_rule(
        python_source="def transform(v): return v",
        mapping=_mapping(),
    )
    assert isinstance(out, TierFailure)
    assert out.tier == "datalog"
    assert "parse_failure" in out.reason


def test_invalid_datalog_returns_syntax_error_failure():
    rule = "```datalog\ntarget(X) :- broken_syntax(\n```"
    llm_synthesizer.set_llm_backend(
        lambda s, u, k: llm_synthesizer._BackendResponse(text=rule, model_id="x")
    )
    out = emit_datalog_rule(
        python_source="def transform(v): return v",
        mapping=_mapping(),
    )
    assert isinstance(out, TierFailure)
    assert "datalog_syntax_error" in out.reason


def test_verify_against_python_accepts_parseable_rule():
    out = verify_datalog_against_python(
        "target(X, Y) :- legacy(X, Y).",
        "def transform(v): return v",
        (),
    )
    assert out is None


def test_verify_against_python_rejects_broken_rule():
    out = verify_datalog_against_python(
        "target(X :- bogus",
        "def transform(v): return v",
        (),
    )
    assert isinstance(out, TierFailure)
    assert "syntax_error" in out.reason
