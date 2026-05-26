"""Tests for column metadata extraction (D1 P2)."""

from __future__ import annotations

import pytest

from omnix.dm._types import ColumnSpec, SchemaSpec, TableSpec
from omnix.dm.d1_schema_understanding.column_metadata import (
    ReadOnlyError,
    extract,
)


class _Cursor:
    def __init__(self, *, read_only=True, rows=None, raise_on_execute=None):
        self._read_only = read_only
        self._rows = rows if rows is not None else []
        self._raise = raise_on_execute
        self.executed: list[str] = []

    def execute(self, sql, params=None):  # noqa: D401
        self.executed.append(sql)
        if self._raise is not None:
            raise self._raise

    def fetchone(self):
        if self._read_only:
            return ("on",)
        return ("off",)

    def fetchall(self):
        return [(r,) for r in self._rows]


class _Conn:
    def __init__(self, **kw):
        self._kw = kw
        self.cursors: list[_Cursor] = []

    def cursor(self):
        c = _Cursor(**self._kw)
        self.cursors.append(c)
        return c


def _mk_schema(dialect="postgres"):
    cols = (
        ColumnSpec(
            name="email",
            raw_type="VARCHAR(255)",
            normalized_type="STRING",
            nullable=True,
            default=None,
            primary_key=False,
            unique=False,
            comment=None,
            dialect_specific={},
        ),
    )
    return SchemaSpec(
        dialect=dialect,
        name="default",
        tables=(TableSpec(name="owner", columns=cols, primary_key=()),),
    )


def test_read_only_verified_success():
    conn = _Conn(read_only=True, rows=["a@x", "b@x", "c@x"])
    ctx = extract(_mk_schema(), conn)
    assert len(ctx) == 1
    # 3 rows fetched
    assert ctx[0].sample_count == 3
    assert set(ctx[0].sample_values) == {"a@x", "b@x", "c@x"}


def test_read_only_failure_halts():
    conn = _Conn(read_only=False)
    with pytest.raises(ReadOnlyError):
        extract(_mk_schema(), conn)


def test_empty_table_surfaces_confidence_note():
    conn = _Conn(read_only=True, rows=[])
    ctx = extract(_mk_schema(), conn)
    assert ctx[0].sample_count == 0
    assert ctx[0].sample_values == ()
    assert any("empty table" in n for n in ctx[0].confidence_notes)


def test_sampling_error_surfaces_not_swallows():
    conn = _Conn(
        read_only=True,
        raise_on_execute=None,
    )
    # We can't make the read-only check pass while making sampling fail with
    # one cursor, so do this: rebuild the conn to give a passing read-only
    # cursor first, then a failing one.
    class _Bicephalic:
        def __init__(self):
            self.calls = 0

        def cursor(self):
            self.calls += 1
            if self.calls == 1:
                return _Cursor(read_only=True)
            return _Cursor(raise_on_execute=RuntimeError("oh no"))

    ctx = extract(_mk_schema(), _Bicephalic())
    assert ctx[0].sample_values == ()
    assert any("sampling failed" in n for n in ctx[0].confidence_notes)


def test_no_connection_still_emits_context():
    """Per the EARS clause, D1 can run without a connection — we get
    confidence_notes flagging it but every column still appears in output."""
    ctx = extract(_mk_schema(), None)
    assert len(ctx) == 1
    assert "no_db_connection" in ctx[0].confidence_notes
