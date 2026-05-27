"""Per-dialect legacy reader tests (P3) — fully mocked, no live DB."""

from __future__ import annotations

import pytest

from omnix.dm._types import ColumnSpec
from omnix.dm.d4_bulk_import.legacy_reader import LegacyReadError, iter_batches


def _col(name: str) -> ColumnSpec:
    return ColumnSpec(
        name=name,
        raw_type="INTEGER",
        normalized_type="INTEGER",
        nullable=False,
        default=None,
        primary_key=name == "id",
        unique=False,
        comment=None,
    )


# ---------------------------------------------------------------------------
# Mock cursor + connection helpers
# ---------------------------------------------------------------------------


class _FakeCursor:
    def __init__(self, rows, *, name=None):
        self._rows = list(rows)
        self.itersize = None
        self.arraysize = None
        self.name = name
        self.executed = None
        self.closed = False

    def execute(self, sql):
        self.executed = sql

    def fetchmany(self, n):
        if not self._rows:
            return []
        chunk, self._rows = self._rows[:n], self._rows[n:]
        return chunk

    def close(self):
        self.closed = True


class _FakePGConn:
    def __init__(self, rows):
        self._cursor = _FakeCursor(rows)

    def cursor(self, *, name=None):
        self._cursor.name = name
        return self._cursor


class _FakeMySQLConn:
    def __init__(self, rows):
        self._cursor = _FakeCursor(rows)

    def cursor(self, SSCursor=False):  # noqa: N803 — mimic MySQLdb signature
        assert SSCursor is True, "must request server-side cursor"
        return self._cursor


class _FakeOracleConn:
    def __init__(self, rows):
        self._cursor = _FakeCursor(rows)

    def cursor(self):
        return self._cursor


class _FakeMongoCollection:
    def __init__(self, docs):
        self._docs = docs

    def find(self, _filter, *, batch_size=100, no_cursor_timeout=False):
        return iter(self._docs)


class _FakeMongoConn:
    def __init__(self, docs):
        self._coll = _FakeMongoCollection(docs)

    def __getitem__(self, name):
        return self._coll


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


def test_pg_happy_path():
    cols = [_col("id"), _col("email")]
    rows = [(i, f"u{i}@x") for i in range(7)]
    conn = _FakePGConn(rows)
    batches = list(
        iter_batches(
            table="owners",
            columns=cols,
            dialect="postgres",
            conn=conn,
            migration_id="m1",
            batch_size=3,
            pk_columns=("id",),
        )
    )
    assert len(batches) == 3
    assert sum(len(b.rows) for b in batches) == 7
    assert conn._cursor.itersize == 3
    assert conn._cursor.closed


def test_mysql_happy_path():
    cols = [_col("id")]
    conn = _FakeMySQLConn([(i,) for i in range(5)])
    batches = list(
        iter_batches(
            table="t",
            columns=cols,
            dialect="mysql",
            conn=conn,
            migration_id="m1",
            batch_size=2,
        )
    )
    assert len(batches) == 3
    assert conn._cursor.arraysize == 2


def test_oracle_happy_path():
    cols = [_col("id")]
    conn = _FakeOracleConn([(i,) for i in range(4)])
    batches = list(
        iter_batches(
            table="t",
            columns=cols,
            dialect="oracle",
            conn=conn,
            migration_id="m1",
            batch_size=2,
        )
    )
    assert len(batches) == 2
    assert conn._cursor.arraysize == 2


def test_mongo_happy_path():
    cols = [_col("name")]
    docs = [{"name": f"n{i}", "_id": i} for i in range(5)]
    conn = _FakeMongoConn(docs)
    batches = list(
        iter_batches(
            table="things",
            columns=cols,
            dialect="mongodb",
            conn=conn,
            migration_id="m1",
            batch_size=3,
        )
    )
    assert sum(len(b.rows) for b in batches) == 5


def test_empty_table_yields_nothing():
    conn = _FakePGConn([])
    out = list(
        iter_batches(
            table="t",
            columns=[_col("id")],
            dialect="postgres",
            conn=conn,
            migration_id="m1",
            batch_size=10,
        )
    )
    assert out == []


def test_three_batches_for_twelve_thousand_at_five_thousand():
    rows = [(i,) for i in range(12_000)]
    conn = _FakePGConn(rows)
    batches = list(
        iter_batches(
            table="t",
            columns=[_col("id")],
            dialect="postgres",
            conn=conn,
            migration_id="m1",
            batch_size=5_000,
        )
    )
    assert len(batches) == 3
    assert [len(b.rows) for b in batches] == [5_000, 5_000, 2_000]


def test_reconnect_on_transient_error_completes():
    class _FlakyCursor(_FakeCursor):
        def __init__(self, rows):
            super().__init__(rows)
            self._failed = False

        def fetchmany(self, n):
            if not self._failed:
                self._failed = True
                raise ConnectionError("transient")
            return super().fetchmany(n)

    cur = _FlakyCursor([(i,) for i in range(3)])

    class _Conn:
        def cursor(self, *, name=None):
            return cur

    reconnects = {"n": 0}

    def _reconnect():
        reconnects["n"] += 1
        return _Conn()

    out = list(
        iter_batches(
            table="t",
            columns=[_col("id")],
            dialect="postgres",
            conn=_Conn(),
            migration_id="m1",
            batch_size=10,
            reconnect=_reconnect,
        )
    )
    assert sum(len(b.rows) for b in out) == 3
    assert reconnects["n"] >= 1


def test_permanent_error_raises_after_retry_max(monkeypatch):
    monkeypatch.setenv("OMNIX_DM_BULK_RETRY_MAX", "2")

    class _DeadCursor(_FakeCursor):
        def fetchmany(self, n):
            raise RuntimeError("permanently dead")

    class _Conn:
        def cursor(self, *, name=None):
            return _DeadCursor([])

    with pytest.raises(LegacyReadError):
        list(
            iter_batches(
                table="t",
                columns=[_col("id")],
                dialect="postgres",
                conn=_Conn(),
                migration_id="m1",
                batch_size=10,
                reconnect=lambda: _Conn(),
            )
        )


def test_pg_cursor_itersize_is_set():
    conn = _FakePGConn([(1,)])
    list(
        iter_batches(
            table="t",
            columns=[_col("id")],
            dialect="postgres",
            conn=conn,
            migration_id="m1",
            batch_size=42,
        )
    )
    assert conn._cursor.itersize == 42


def test_row_column_values_sorted_by_name():
    cols = [_col("z"), _col("a"), _col("m")]
    rows = [("z1", "a1", "m1")]
    conn = _FakePGConn(rows)
    batches = list(
        iter_batches(
            table="t",
            columns=cols,
            dialect="postgres",
            conn=conn,
            migration_id="m1",
            batch_size=10,
        )
    )
    sorted_names = [name for name, _ in batches[0].rows[0].column_values]
    assert sorted_names == ["a", "m", "z"]


def test_unsupported_dialect_raises():
    with pytest.raises(LegacyReadError):
        list(
            iter_batches(
                table="t",
                columns=[_col("id")],
                dialect="cassandra",  # type: ignore[arg-type]
                conn=object(),
                migration_id="m1",
            )
        )
