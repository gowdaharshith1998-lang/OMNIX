"""Tests for column embedder (D1 P3).

Uses the deterministic hash-based backend so we don't depend on a HuggingFace
model download in CI. The semantic-quality tests live in P3's matcher tests
where the real backend can be exercised when available.
"""

from __future__ import annotations

import numpy as np
import pytest

from omnix.dm._types import ColumnContext, ColumnSpec
from omnix.dm.d1_schema_understanding.column_embedder import (
    EMBED_DIM,
    _hash_based_backend,
    build_embedding_input,
    embed,
    set_embedding_backend,
)


@pytest.fixture(autouse=True)
def _hash_backend():
    set_embedding_backend(_hash_based_backend)
    yield
    set_embedding_backend(None)


def _ctx(name="email", table="owner", typ="VARCHAR(255)"):
    return ColumnContext(
        column=ColumnSpec(
            name=name,
            raw_type=typ,
            normalized_type="STRING",
            nullable=True,
            default=None,
            primary_key=False,
            unique=False,
            comment=None,
            dialect_specific={},
        ),
        table_name=table,
        sample_values=("a@x.com", "b@x.com"),
        sample_count=2,
        codebase_usage=(),
        confidence_notes=(),
    )


def test_embedding_is_deterministic():
    v1 = embed(_ctx())
    v2 = embed(_ctx())
    assert np.allclose(v1, v2)


def test_embedding_shape_and_dtype():
    v = embed(_ctx())
    assert v.shape == (EMBED_DIM,)
    assert v.dtype == np.float32


def test_different_inputs_give_different_vectors():
    v1 = embed(_ctx(name="email"))
    v2 = embed(_ctx(name="totally_unrelated_xyz"))
    assert not np.allclose(v1, v2)


def test_prompt_template_includes_all_inputs():
    txt = build_embedding_input(_ctx())
    assert "COLUMN: email" in txt
    assert "TABLE: owner" in txt
    assert "VARCHAR(255)" in txt
    assert "a@x.com" in txt
