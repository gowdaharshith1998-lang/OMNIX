"""Per-dialect streaming legacy reader.

Yields :class:`Batch` instances of ``OMNIX_DM_BULK_BATCH_SIZE`` rows. Each
dialect uses its native server-side cursor mechanism so memory stays
bounded regardless of source-table size:

* PostgreSQL — psycopg2 named cursor with ``itersize``
* MySQL — ``SSCursor`` (server-side; no client buffering)
* Oracle — ``cursor.arraysize`` matching batch size
* MongoDB — ``find(batch_size=...)`` iterator

The reader's job is bytes-faithful row capture — typing problems become
the transformer's quarantine concern, not the reader's.
"""

from __future__ import annotations

import os
import time
from typing import Any, Callable, Iterable, Iterator, List, Optional

from omnix.dm._types import Batch, ColumnSpec, Dialect
from omnix.dm.d4_bulk_import._primitives import make_batch_id, normalize_row


class LegacyReadError(RuntimeError):
    """Raised after retry exhaustion on a transient legacy-read failure."""


def _env_batch_size(override: Optional[int]) -> int:
    if override is not None:
        return override
    return int(os.environ.get("OMNIX_DM_BULK_BATCH_SIZE", "5000"))


def _env_retry_max() -> int:
    return int(os.environ.get("OMNIX_DM_BULK_RETRY_MAX", "3"))


def _pk_repr(pk_columns: tuple, row: dict) -> str:
    if not pk_columns:
        return repr(())
    return repr(tuple(row.get(c) for c in pk_columns))


def iter_batches(
    *,
    table: str,
    columns: List[ColumnSpec],
    dialect: Dialect,
    conn: Any,
    migration_id: str,
    batch_size: Optional[int] = None,
    snapshot_lsn: Optional[str] = None,
    pk_columns: tuple = (),
    reconnect: Optional[Callable[[], Any]] = None,
) -> Iterator[Batch]:
    """Yield :class:`Batch` records from ``table`` in ``conn`` using the
    dialect's server-side cursor mechanism. ``reconnect`` is an optional
    callable that returns a fresh connection if a transient error fires
    mid-iteration; we retry up to ``OMNIX_DM_BULK_RETRY_MAX`` times."""
    size = _env_batch_size(batch_size)
    if dialect == "postgres":
        yield from _pg_iter(
            table, columns, conn, migration_id, size, snapshot_lsn, pk_columns, reconnect
        )
    elif dialect == "mysql":
        yield from _mysql_iter(
            table, columns, conn, migration_id, size, snapshot_lsn, pk_columns, reconnect
        )
    elif dialect == "oracle":
        yield from _oracle_iter(
            table, columns, conn, migration_id, size, snapshot_lsn, pk_columns, reconnect
        )
    elif dialect == "mongodb":
        yield from _mongo_iter(
            table, columns, conn, migration_id, size, snapshot_lsn, pk_columns, reconnect
        )
    else:
        raise LegacyReadError(f"unsupported dialect for reader: {dialect!r}")


# ---------------------------------------------------------------------------
# Per-dialect helpers (all accept duck-typed connections so tests can mock).
# ---------------------------------------------------------------------------


def _identifier(name: str) -> str:
    """Local minimal quote_ident — reject anything with a double quote."""
    if '"' in name or "\x00" in name:
        raise LegacyReadError(f"unsafe identifier {name!r}")
    return f'"{name}"'


def _column_list(columns: List[ColumnSpec]) -> str:
    return ", ".join(_identifier(c.name) for c in columns)


def _emit_batch(
    *,
    migration_id: str,
    table: str,
    batch_no: int,
    rows: List[dict],
    snapshot_lsn: Optional[str],
    pk_columns: tuple,
) -> Batch:
    normalized = tuple(
        normalize_row(table, _pk_repr(pk_columns, r), r) for r in rows
    )
    return Batch(
        migration_id=migration_id,
        table=table,
        batch_no=batch_no,
        batch_id=make_batch_id(migration_id, table, batch_no),
        rows=normalized,
        snapshot_lsn=snapshot_lsn,
    )


def _with_retry(action: Callable[[], Any], reconnect: Optional[Callable[[], Any]]):
    attempts = 0
    last_exc: Optional[Exception] = None
    while attempts < _env_retry_max():
        try:
            return action()
        except Exception as exc:  # noqa: BLE001 — broad surface; we re-raise on exhaustion
            last_exc = exc
            attempts += 1
            if reconnect is None:
                raise LegacyReadError(f"read failed: {exc}") from exc
            time.sleep(min(2 ** attempts, 5))
            reconnect()
    raise LegacyReadError(f"read failed after {attempts} retries: {last_exc}")


def _pg_iter(
    table: str,
    columns: List[ColumnSpec],
    conn: Any,
    migration_id: str,
    size: int,
    snapshot_lsn: Optional[str],
    pk_columns: tuple,
    reconnect: Optional[Callable[[], Any]],
) -> Iterator[Batch]:
    col_list = _column_list(columns)
    sql = f'SELECT {col_list} FROM {_identifier(table)}'
    cur = conn.cursor(name=f"omnix_dm_{migration_id}_{table}")
    cur.itersize = size
    cur.execute(sql)
    column_names = [c.name for c in columns]
    batch_no = 0
    while True:
        rows = _with_retry(lambda: cur.fetchmany(size), reconnect)
        if not rows:
            break
        dict_rows = [dict(zip(column_names, r)) for r in rows]
        yield _emit_batch(
            migration_id=migration_id,
            table=table,
            batch_no=batch_no,
            rows=dict_rows,
            snapshot_lsn=snapshot_lsn,
            pk_columns=pk_columns,
        )
        batch_no += 1
    cur.close()


def _mysql_iter(
    table: str,
    columns: List[ColumnSpec],
    conn: Any,
    migration_id: str,
    size: int,
    snapshot_lsn: Optional[str],
    pk_columns: tuple,
    reconnect: Optional[Callable[[], Any]],
) -> Iterator[Batch]:
    col_list = _column_list(columns)
    sql = f"SELECT {col_list} FROM {_identifier(table)}"
    # MySQLdb-style SSCursor signature
    try:
        cur = conn.cursor(SSCursor=True)
    except TypeError:
        # PyMySQL: cursors.SSCursor passed as class
        from pymysql.cursors import SSCursor  # type: ignore[import-not-found]

        cur = conn.cursor(SSCursor)
    cur.arraysize = size
    cur.execute(sql)
    column_names = [c.name for c in columns]
    batch_no = 0
    while True:
        rows = _with_retry(lambda: cur.fetchmany(size), reconnect)
        if not rows:
            break
        dict_rows = [dict(zip(column_names, r)) for r in rows]
        yield _emit_batch(
            migration_id=migration_id,
            table=table,
            batch_no=batch_no,
            rows=dict_rows,
            snapshot_lsn=snapshot_lsn,
            pk_columns=pk_columns,
        )
        batch_no += 1
    cur.close()


def _oracle_iter(
    table: str,
    columns: List[ColumnSpec],
    conn: Any,
    migration_id: str,
    size: int,
    snapshot_lsn: Optional[str],
    pk_columns: tuple,
    reconnect: Optional[Callable[[], Any]],
) -> Iterator[Batch]:
    col_list = _column_list(columns)
    sql = f"SELECT {col_list} FROM {_identifier(table)}"
    cur = conn.cursor()
    cur.arraysize = size
    cur.execute(sql)
    column_names = [c.name for c in columns]
    batch_no = 0
    while True:
        rows = _with_retry(lambda: cur.fetchmany(size), reconnect)
        if not rows:
            break
        dict_rows = [dict(zip(column_names, r)) for r in rows]
        yield _emit_batch(
            migration_id=migration_id,
            table=table,
            batch_no=batch_no,
            rows=dict_rows,
            snapshot_lsn=snapshot_lsn,
            pk_columns=pk_columns,
        )
        batch_no += 1
    cur.close()


def _mongo_iter(
    table: str,
    columns: List[ColumnSpec],
    conn: Any,
    migration_id: str,
    size: int,
    snapshot_lsn: Optional[str],
    pk_columns: tuple,
    reconnect: Optional[Callable[[], Any]],
) -> Iterator[Batch]:
    collection = conn[table]
    cursor = collection.find({}, batch_size=size, no_cursor_timeout=False)
    batch_no = 0
    buf: List[dict] = []
    column_names = [c.name for c in columns]
    for doc in cursor:
        row = {name: doc.get(name) for name in column_names}
        if "_id" in doc and "_id" not in row:
            row["_id"] = doc["_id"]
        buf.append(row)
        if len(buf) >= size:
            yield _emit_batch(
                migration_id=migration_id,
                table=table,
                batch_no=batch_no,
                rows=buf,
                snapshot_lsn=snapshot_lsn,
                pk_columns=pk_columns or ("_id",),
            )
            buf = []
            batch_no += 1
    if buf:
        yield _emit_batch(
            migration_id=migration_id,
            table=table,
            batch_no=batch_no,
            rows=buf,
            snapshot_lsn=snapshot_lsn,
            pk_columns=pk_columns or ("_id",),
        )


__all__ = ["LegacyReadError", "iter_batches"]
