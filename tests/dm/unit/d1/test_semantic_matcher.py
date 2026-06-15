"""Tests for the Hungarian semantic matcher (D1 P3)."""

from __future__ import annotations

import os

import numpy as np
import pytest

from omnix.dm._types import ColumnContext, ColumnSpec
from omnix.dm.d1_schema_understanding import column_embedder
from omnix.dm.d1_schema_understanding.semantic_matcher import (
    LOW_CONFIDENCE_FLOOR,
    OK_THRESHOLD_DEFAULT,
    match,
)


def _ctx(name, table="t", typ="VARCHAR"):
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
    )


def _force_embed_backend(monkeypatch, name_to_vec):
    """Force every legacy column to embed as ``name_to_vec[name]``."""
    def fake_embed(ctx):
        v = name_to_vec.get(ctx.column.name)
        if v is None:
            # Default: random-ish low-magnitude
            v = np.zeros(column_embedder.EMBED_DIM, dtype=np.float32)
        return v.astype(np.float32)

    monkeypatch.setattr(
        "omnix.dm.d1_schema_understanding.semantic_matcher.embed", fake_embed
    )


def _onehot(idx, dim=column_embedder.EMBED_DIM):
    v = np.zeros(dim, dtype=np.float32)
    v[idx] = 1.0
    return v


def test_no_legacy_returns_empty():
    res = match((), (_ctx("a"),))
    assert res == ()


def test_no_target_marks_no_match():
    res = match((_ctx("email"), _ctx("name")), ())
    assert len(res) == 2
    assert all(m.status == "no_match" for m in res)
    assert all(m.target_column is None for m in res)


def test_perfect_match_is_ok(monkeypatch):
    name_to_vec = {
        "email": _onehot(0),
        "address": _onehot(1),
    }
    _force_embed_backend(monkeypatch, name_to_vec)
    legacy = (_ctx("email", table="L"), _ctx("address", table="L"))
    target = (_ctx("email", table="T"), _ctx("address", table="T"))
    res = match(legacy, target)
    assert {m.legacy_column for m in res} == {"email", "address"}
    statuses = {m.legacy_column: m.status for m in res}
    assert statuses["email"] == "ok"
    assert statuses["address"] == "ok"


def test_no_legacy_column_dropped(monkeypatch):
    """Honesty invariant: every legacy column must appear in the output."""
    legacy = tuple(_ctx(f"col{i}", table="L") for i in range(20))
    target = (_ctx("totally_unrelated", table="T"),)
    _force_embed_backend(
        monkeypatch,
        {f"col{i}": _onehot(i) for i in range(20)} | {"totally_unrelated": _onehot(99)},
    )
    res = match(legacy, target)
    assert len(res) == len(legacy)
    # Most will be no_match since target is unrelated
    assert sum(1 for m in res if m.status == "no_match") >= 19


def test_low_confidence_path(monkeypatch):
    """When the threshold is high enough that even the best match is below
    OK_THRESHOLD but above LOW_CONFIDENCE_FLOOR, the mapping is flagged for
    operator review."""
    # Two vectors with cosine ~ 0.7 (above floor, below ok)
    a = _onehot(0)
    b = np.zeros(column_embedder.EMBED_DIM, dtype=np.float32)
    b[0] = 0.7
    b[1] = np.sqrt(1 - 0.7 ** 2)

    monkeypatch.setattr(
        "omnix.dm.d1_schema_understanding.semantic_matcher.embed",
        lambda c: a if c.column.name == "x" else b,
    )
    res = match((_ctx("x", table="L"),), (_ctx("y", table="T"),))
    assert res[0].status == "low_confidence"
    assert "operator review" in res[0].rationale.lower()


def test_top3_candidates_surfaced(monkeypatch):
    """Even ambiguous mappings surface their top-3 alternates so the operator
    can pick from a ranked shortlist."""
    name_to_vec = {
        "primary_email": np.array([1.0, 0.0, 0.0] + [0.0] * (column_embedder.EMBED_DIM - 3), dtype=np.float32),
        "email": np.array([0.95, 0.05, 0.0] + [0.0] * (column_embedder.EMBED_DIM - 3), dtype=np.float32),
        "email_address": np.array([0.9, 0.1, 0.0] + [0.0] * (column_embedder.EMBED_DIM - 3), dtype=np.float32),
        "contact": np.array([0.7, 0.5, 0.0] + [0.0] * (column_embedder.EMBED_DIM - 3), dtype=np.float32),
    }
    # normalize
    name_to_vec = {k: v / np.linalg.norm(v) for k, v in name_to_vec.items()}
    _force_embed_backend(monkeypatch, name_to_vec)
    legacy = (_ctx("primary_email", table="L"),)
    target = (_ctx("email", table="T"), _ctx("email_address", table="T"), _ctx("contact", table="T"))
    res = match(legacy, target)
    assert len(res[0].candidates) == 3
    # The first candidate should be the best
    assert res[0].candidates[0][2] >= res[0].candidates[1][2]


def test_env_threshold_override(monkeypatch):
    """OMNIX_DM_CONFIDENCE_THRESHOLD overrides the default."""
    monkeypatch.setenv("OMNIX_DM_CONFIDENCE_THRESHOLD", "0.50")
    # cosine ~ 0.6 — would be low_confidence at default 0.85 but ok at 0.50
    a = _onehot(0)
    b = np.zeros(column_embedder.EMBED_DIM, dtype=np.float32)
    b[0] = 0.7
    b[1] = np.sqrt(1 - 0.7 ** 2)

    monkeypatch.setattr(
        "omnix.dm.d1_schema_understanding.semantic_matcher.embed",
        lambda c: a if c.column.name == "x" else b,
    )
    res = match((_ctx("x", table="L"),), (_ctx("y", table="T"),))
    assert res[0].status == "ok"
