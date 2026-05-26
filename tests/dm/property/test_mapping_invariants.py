"""Hypothesis-based property tests for D1 mapping invariants.

The central invariant (Codex axiom): no legacy column may be silently dropped
from the matcher's output. ``len(result) == len(legacy_ctx)`` for ALL inputs.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from omnix.dm._types import ColumnContext, ColumnSpec
from omnix.dm.d1_schema_understanding import column_embedder
from omnix.dm.d1_schema_understanding.column_embedder import (
    _hash_based_backend,
    embed,
    set_embedding_backend,
)
from omnix.dm.d1_schema_understanding.semantic_matcher import match


@pytest.fixture(autouse=True)
def _hash_backend():
    set_embedding_backend(_hash_based_backend)
    yield
    set_embedding_backend(None)


_name_st = st.text(
    alphabet=st.characters(whitelist_categories=("L", "N"), whitelist_characters="_"),
    min_size=1,
    max_size=15,
).filter(lambda s: s[0].isalpha() or s[0] == "_")


def _make_ctx(name, table="t"):
    return ColumnContext(
        column=ColumnSpec(
            name=name,
            raw_type="VARCHAR",
            normalized_type="STRING",
            nullable=True,
            default=None,
            primary_key=False,
            unique=False,
            comment=None,
            dialect_specific={},
        ),
        table_name=table,
    )


@given(
    legacy_names=st.lists(_name_st, min_size=1, max_size=12, unique=True),
    target_names=st.lists(_name_st, min_size=0, max_size=12, unique=True),
)
@settings(max_examples=50, deadline=2_000)
def test_no_legacy_column_silently_dropped(legacy_names, target_names):
    legacy = tuple(_make_ctx(n, table="L") for n in legacy_names)
    target = tuple(_make_ctx(n, table="T") for n in target_names)
    res = match(legacy, target)
    assert len(res) == len(legacy)
    legacy_set = {(c.table_name, c.column.name) for c in legacy}
    output_set = {(m.legacy_table, m.legacy_column) for m in res}
    assert output_set == legacy_set


@given(name=_name_st)
@settings(max_examples=30, deadline=2_000)
def test_embedding_is_deterministic(name):
    ctx = _make_ctx(name)
    v1 = embed(ctx)
    v2 = embed(ctx)
    assert np.allclose(v1, v2)
    assert v1.shape == (column_embedder.EMBED_DIM,)
