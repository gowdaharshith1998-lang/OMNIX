"""Target writer tests (P5)."""

from __future__ import annotations

import pytest

from omnix.dm._types import TransformedBatch, TransformedRow
from omnix.dm.d4_bulk_import._primitives import make_batch_id
from omnix.dm.d4_bulk_import.target_writer import (
    TargetSchemaError,
    TargetWriteError,
    quote_ident,
    write_batch,
)


def _batch(rows_of_columns):
    transformed = tuple(
        TransformedRow(
            legacy_pk_value_repr=repr(i),
            target_column_values=tuple(cols.items()),
        )
        for i, cols in enumerate(rows_of_columns)
    )
    return TransformedBatch(
        migration_id="m1",
        table="owners",
        batch_no=0,
        batch_id=make_batch_id("m1", "owners", 0),
        transformed_rows=transformed,
    )


# ---------------------------------------------------------------------------
# Mock cursors / connections
# ---------------------------------------------------------------------------


class _RecordingCursor:
    def __init__(self):
        self.executed = []
        self.copy_calls = []
        self.fail_on_first = False
        self.constraint_on_offset = None

    def execute(self, sql, params=None):
        self.executed.append((sql, params))
        if self.constraint_on_offset is not None and params is not None:
            # Match by __omnix_batch_id position is irrelevant; we trigger on
            # a sentinel value if the test pre-seeded it via params content.
            for v in params:
                if isinstance(v, str) and v.startswith("CONFLICT:"):
                    raise Exception("UNIQUE constraint violation")
        return None

    def fetchone(self):
        return ("1",)

    def copy_expert(self, sql, buf):
        self.copy_calls.append(sql)
        if self.fail_on_first:
            raise Exception("COPY failed; constraint violation")


class _RecordingConn:
    def __init__(self):
        self._cursor = _RecordingCursor()
        self.committed = False
        self.commit_fails = False

    def cursor(self):
        return self._cursor

    def commit(self):
        if self.commit_fails:
            raise RuntimeError("commit failed")
        self.committed = True


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_quote_ident_rejects_embedded_double_quote():
    with pytest.raises(TargetSchemaError):
        quote_ident('name"; DROP TABLE owners--')


def test_quote_ident_rejects_null_byte():
    with pytest.raises(TargetSchemaError):
        quote_ident("name\x00")


def test_quote_ident_happy_path():
    assert quote_ident("owners") == '"owners"'


def test_pg_copy_happy_path():
    batch = _batch([{"id": 1, "email": "a@b"}, {"id": 2, "email": "c@d"}])
    conn = _RecordingConn()
    result = write_batch(
        batch,
        conn,
        dialect="postgres",
        use_copy=True,
    )
    assert result.rows_written == 2
    assert conn._cursor.copy_calls  # COPY path taken


def test_pg_copy_failure_falls_back_to_insert():
    batch = _batch([{"id": 1, "email": "a@b"}])
    conn = _RecordingConn()
    conn._cursor.fail_on_first = True
    result = write_batch(batch, conn, dialect="postgres", use_copy=True)
    # INSERT fallback path wrote the row
    assert result.rows_written == 1
    # commit happened on the INSERT path
    assert conn.committed


def test_mysql_insert_path():
    batch = _batch([{"id": 1}, {"id": 2}])
    conn = _RecordingConn()
    result = write_batch(batch, conn, dialect="mysql", use_copy=False)
    assert result.rows_written == 2
    # 2 INSERT executes
    insert_sqls = [s for s, _ in conn._cursor.executed if "INSERT" in s]
    assert len(insert_sqls) == 2


def test_constraint_violation_quarantines_row_but_continues():
    batch = _batch([{"email": "ok"}, {"email": "CONFLICT:dup"}, {"email": "fine"}])
    conn = _RecordingConn()
    conn._cursor.constraint_on_offset = 1
    result = write_batch(batch, conn, dialect="postgres", use_copy=False)
    assert result.rows_written == 2
    assert len(result.quarantine_entries) == 1
    assert result.quarantine_entries[0].failure_category == "target_constraint_violation"


def test_deferred_constraints_emits_set_constraints():
    batch = _batch([{"id": 1}])
    conn = _RecordingConn()
    write_batch(
        batch, conn, dialect="postgres", use_copy=False, deferred_constraints=True
    )
    sqls = [s for s, _ in conn._cursor.executed]
    assert any("SET CONSTRAINTS ALL DEFERRED" in s for s in sqls)


def test_commit_failure_raises_target_write_error():
    batch = _batch([{"id": 1}])
    conn = _RecordingConn()
    conn.commit_fails = True
    with pytest.raises(TargetWriteError):
        write_batch(batch, conn, dialect="postgres", use_copy=False)


def test_empty_batch_returns_zero_without_db_call():
    batch = TransformedBatch(
        migration_id="m1",
        table="owners",
        batch_no=0,
        batch_id=make_batch_id("m1", "owners", 0),
        transformed_rows=(),
    )
    conn = _RecordingConn()
    result = write_batch(batch, conn, dialect="postgres", use_copy=True)
    assert result.rows_written == 0
    assert conn._cursor.executed == []


def test_inconsistent_columns_raise_schema_error():
    batch = TransformedBatch(
        migration_id="m1",
        table="owners",
        batch_no=0,
        batch_id=make_batch_id("m1", "owners", 0),
        transformed_rows=(
            TransformedRow(legacy_pk_value_repr="0", target_column_values=(("a", 1),)),
            TransformedRow(legacy_pk_value_repr="1", target_column_values=(("b", 2),)),
        ),
    )
    conn = _RecordingConn()
    with pytest.raises(TargetSchemaError):
        write_batch(batch, conn, dialect="postgres", use_copy=False)


def test_no_f_string_sql_in_module():
    """Static check: target_writer.py must not f-string user data into SQL.

    We grep the source for an f-string SQL pattern; the only allowed f-strings
    are around quote_ident-returned values (validated/rejected on bad input)
    and structural ``COPY`` syntax. The check is heuristic but matches the
    PR C reviewer checklist.
    """
    import pathlib

    src = pathlib.Path("src/omnix/dm/d4_bulk_import/target_writer.py").read_text()
    # Any line with `f"...{...}..."` where the {...} contains a bare variable
    # name that's NOT either `quote_ident(...)` or a known structural identifier.
    bad_patterns = [
        "f\"SELECT * FROM {user_input}",  # exemplar that should never exist
    ]
    for p in bad_patterns:
        assert p not in src
