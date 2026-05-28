"""PG replication-connection helpers — psycopg2 fully mocked."""

from __future__ import annotations

import sys
import types

import pytest


@pytest.fixture
def mock_psycopg2(monkeypatch):
    """Inject a minimal psycopg2 stub into sys.modules so the helpers import
    cleanly without a real PG."""
    mod = types.ModuleType("psycopg2")
    extras = types.ModuleType("psycopg2.extras")

    class LogicalReplicationConnection:
        pass

    extras.LogicalReplicationConnection = LogicalReplicationConnection

    captured = {}

    def _connect(dsn, *, connection_factory=None):
        captured["dsn"] = dsn
        captured["factory"] = connection_factory
        return _FakeConn()

    mod.connect = _connect
    mod.extras = extras
    monkeypatch.setitem(sys.modules, "psycopg2", mod)
    monkeypatch.setitem(sys.modules, "psycopg2.extras", extras)
    return captured


class _FakeCursor:
    def __init__(self):
        self.executed = []
        self.queue = []

    def execute(self, sql, params=None):
        self.executed.append((sql, params))

    def fetchone(self):
        return self.queue.pop(0) if self.queue else None


class _FakeConn:
    def __init__(self):
        self._cursor = _FakeCursor()

    def cursor(self):
        return self._cursor

    def commit(self):
        pass


def test_open_replication_connection_passes_factory(mock_psycopg2):
    from omnix.dm.d5_change_data_capture.pg_adapter.connection import (
        open_replication_connection,
    )

    open_replication_connection("postgresql://user@host/db")
    assert mock_psycopg2["dsn"] == "postgresql://user@host/db"
    assert mock_psycopg2["factory"] is not None


def test_ensure_publication_creates_when_missing(mock_psycopg2):
    from omnix.dm.d5_change_data_capture.pg_adapter.connection import (
        ensure_publication,
    )

    conn = _FakeConn()
    conn._cursor.queue = [None]  # not exists
    ensure_publication(conn, "omnix_pub")
    sqls = [s for s, _ in conn._cursor.executed]
    assert any("CREATE PUBLICATION" in s for s in sqls)


def test_ensure_publication_noop_when_exists(mock_psycopg2):
    from omnix.dm.d5_change_data_capture.pg_adapter.connection import (
        ensure_publication,
    )

    conn = _FakeConn()
    conn._cursor.queue = [(1,)]  # exists
    ensure_publication(conn, "omnix_pub")
    sqls = [s for s, _ in conn._cursor.executed]
    assert not any("CREATE PUBLICATION" in s for s in sqls)


def test_ensure_slot_creates_when_missing(mock_psycopg2):
    from omnix.dm.d5_change_data_capture.pg_adapter.connection import ensure_slot

    conn = _FakeConn()
    conn._cursor.queue = [None]
    ensure_slot(conn, "omnix_slot")
    sqls = [s for s, _ in conn._cursor.executed]
    assert any("pg_create_logical_replication_slot" in s for s in sqls)


def test_ensure_slot_noop_when_exists(mock_psycopg2):
    from omnix.dm.d5_change_data_capture.pg_adapter.connection import ensure_slot

    conn = _FakeConn()
    conn._cursor.queue = [(1,)]
    ensure_slot(conn, "omnix_slot")
    sqls = [s for s, _ in conn._cursor.executed]
    assert not any("pg_create_logical_replication_slot" in s for s in sqls)


def test_publication_name_rejects_quote(mock_psycopg2):
    from omnix.dm.d5_change_data_capture.pg_adapter.connection import (
        ensure_publication,
    )

    conn = _FakeConn()
    conn._cursor.queue = [None]
    with pytest.raises(ValueError):
        ensure_publication(conn, 'bad"name')
