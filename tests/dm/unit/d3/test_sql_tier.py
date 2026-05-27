"""Tests for the SQL CASE tier emitter."""

from __future__ import annotations

import pytest

from omnix.dm._types import ColumnMapping, TierFailure
from omnix.dm.d3_transformation_synthesis import llm_synthesizer
from omnix.dm.d3_transformation_synthesis.sql_tier import (
    emit_sql_case,
    verify_sql_against_python,
)


@pytest.fixture(autouse=True)
def _reset_backend():
    llm_synthesizer.set_llm_backend(None)
    yield
    llm_synthesizer.set_llm_backend(None)


def _mapping():
    return ColumnMapping(
        legacy_table="owners",
        legacy_column="email",
        target_table="owners",
        target_column="email",
        confidence=0.95,
        status="ok",
    )


def test_happy_path_passthrough():
    backend_called = {"n": 0}

    def _backend(s, u, k):
        backend_called["n"] += 1
        return llm_synthesizer._BackendResponse(
            text="```sql\nlegacy_col\n```",
            model_id="x",
        )

    llm_synthesizer.set_llm_backend(_backend)
    out = emit_sql_case(
        python_source="def transform(v): return v",
        mapping=_mapping(),
    )
    assert out == "legacy_col"
    assert backend_called["n"] == 1


def test_missing_sql_block_returns_tier_failure():
    llm_synthesizer.set_llm_backend(
        lambda s, u, k: llm_synthesizer._BackendResponse(text="no fences", model_id="x")
    )
    out = emit_sql_case(
        python_source="def transform(v): return v",
        mapping=_mapping(),
    )
    assert isinstance(out, TierFailure)
    assert out.tier == "sql"
    assert "parse_failure" in out.reason


def test_empty_sql_block_returns_tier_failure():
    llm_synthesizer.set_llm_backend(
        lambda s, u, k: llm_synthesizer._BackendResponse(text="```sql\n\n```", model_id="x")
    )
    out = emit_sql_case(
        python_source="def transform(v): return v",
        mapping=_mapping(),
    )
    assert isinstance(out, TierFailure)
    assert "empty" in out.reason


def test_backend_exception_returns_tier_failure():
    def _raise(s, u, k):
        raise RuntimeError("connection refused")

    llm_synthesizer.set_llm_backend(_raise)
    out = emit_sql_case(
        python_source="def transform(v): return v",
        mapping=_mapping(),
    )
    assert isinstance(out, TierFailure)
    assert "api_failure" in out.reason


def test_sentinel_to_null_case():
    sql = (
        "```sql\n"
        "CASE WHEN legacy_col IN ('N/A','NULL','TBD') THEN NULL ELSE legacy_col END\n"
        "```"
    )
    llm_synthesizer.set_llm_backend(
        lambda s, u, k: llm_synthesizer._BackendResponse(text=sql, model_id="x")
    )
    out = emit_sql_case(
        python_source="def transform(v):\n    if v in ('N/A','NULL','TBD'): return None\n    return v",
        mapping=_mapping(),
    )
    assert isinstance(out, str)
    assert "CASE WHEN" in out


def test_verify_without_pg_returns_infrastructure_unavailable():
    out = verify_sql_against_python("SELECT 1", "def transform(v): return v", ())
    assert isinstance(out, TierFailure)
    assert "infrastructure_unavailable" in out.reason
