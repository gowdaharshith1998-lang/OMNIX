"""Column metadata extraction — runs read-only against the legacy DB.

Public surface:
    extract(schema, conn) -> tuple[ColumnContext, ...]

Contract (EARS):
  * When called with a read-only DB connection, samples up to
    ``MAX_SAMPLE_VALUES`` distinct values per column via parameterized SQL.
  * When the connection is **not** read-only, halts with ``ReadOnlyError``.
  * When sampling fails (empty table, permission error, etc), surfaces it
    via ``confidence_notes`` rather than swallowing.
  * Bridges into ``codebase_memory_bridge`` for per-column code-usage; that
    bridge is itself non-mutating and surfaces missing-graph honestly.

The connection object is duck-typed: it must expose ``cursor()`` returning a
DB-API 2.0-like cursor (``.execute``, ``.fetchall``, ``.fetchone``). We never
issue mutating SQL.
"""

from __future__ import annotations

from typing import Any, List, Optional, Protocol, Tuple

from omnix.dm._types import (
    ColumnContext,
    ColumnSpec,
    Dialect,
    SchemaSpec,
    TableSpec,
)
from omnix.dm.d1_schema_understanding.codebase_memory_bridge import (
    lookup_column_usage,
)

MAX_SAMPLE_VALUES = 100


class ReadOnlyError(RuntimeError):
    """Raised when the supplied connection is not in a verified read-only mode."""


class DBConnection(Protocol):
    """Minimal DB-API 2.0 surface used by the metadata extractor."""

    def cursor(self) -> Any: ...


def _verify_read_only(conn: DBConnection, dialect: Dialect) -> None:
    """Issue the dialect-appropriate read-only sentinel query. On any sign of
    write privilege OR query failure we halt — silently treating an unknown
    connection as read-only would violate the honesty invariant."""
    cursor = conn.cursor()
    if dialect == "postgres":
        cursor.execute("SHOW transaction_read_only")
        row = cursor.fetchone()
        # PG returns 'on' / 'off' or similar — treat anything but a positive
        # 'on'/'true' as not-verified.
        val = (row[0] if row else "").lower() if isinstance(row, (tuple, list)) else str(row).lower()
        if val not in {"on", "true", "1"}:
            raise ReadOnlyError(
                "postgres connection is not in read-only transaction mode "
                f"(transaction_read_only={val!r})"
            )
    elif dialect == "mysql":
        cursor.execute("SELECT @@read_only")
        row = cursor.fetchone()
        val = row[0] if isinstance(row, (tuple, list)) else row
        if not val:
            raise ReadOnlyError(
                f"mysql connection is not read-only (@@read_only={val!r})"
            )
    elif dialect == "oracle":
        # Oracle: query v$instance.open_mode — 'READ ONLY' or similar.
        cursor.execute(
            "SELECT OPEN_MODE FROM V$DATABASE"
        )
        row = cursor.fetchone()
        val = (row[0] if row else "").upper() if isinstance(row, (tuple, list)) else str(row).upper()
        if "READ ONLY" not in val:
            raise ReadOnlyError(
                f"oracle connection is not read-only (OPEN_MODE={val!r})"
            )
    elif dialect == "mongodb":
        # Mongo: read-only enforced at user privileges; treat the
        # ``readOnly`` attribute on the conn or driver session as the signal.
        if not getattr(conn, "read_only", False):
            raise ReadOnlyError(
                "mongo connection does not advertise read_only=True"
            )


def _quote_ident(name: str, dialect: Dialect) -> str:
    """Dialect-appropriate identifier quoting. Used only for trusted identifiers
    that come from a parsed SchemaSpec — never from user-supplied free text."""
    if dialect == "mysql":
        # Defensive: reject any backtick in the name.
        if "`" in name:
            raise ValueError(f"refusing to quote identifier containing backtick: {name!r}")
        return f"`{name}`"
    # Default: ANSI double-quotes (PG, Oracle, others)
    if '"' in name:
        raise ValueError(f"refusing to quote identifier containing dquote: {name!r}")
    return f'"{name}"'


def _sample_sql(dialect: Dialect, table: str, column: str, limit: int) -> str:
    """Build the dialect-appropriate sampling SQL. Identifiers are quoted via
    ``_quote_ident``; ``limit`` is an int we pass directly into the string
    (DB-API placeholders aren't always allowed for LIMIT, and ``int(limit)``
    is type-safe)."""
    tq = _quote_ident(table, dialect)
    cq = _quote_ident(column, dialect)
    n = int(limit)
    if dialect == "postgres":
        return f"SELECT DISTINCT {cq} FROM {tq} ORDER BY RANDOM() LIMIT {n}"
    if dialect == "mysql":
        return f"SELECT DISTINCT {cq} FROM {tq} ORDER BY RAND() LIMIT {n}"
    if dialect == "oracle":
        return (
            f"SELECT * FROM (SELECT DISTINCT {cq} FROM {tq} "
            f"ORDER BY DBMS_RANDOM.VALUE) WHERE ROWNUM <= {n}"
        )
    raise ValueError(f"no sample SQL for dialect {dialect}")


def _extract_column(
    conn: DBConnection,
    dialect: Dialect,
    table: TableSpec,
    column: ColumnSpec,
) -> ColumnContext:
    notes: List[str] = []
    sample_values: Tuple[str, ...] = ()
    sample_count = 0
    if dialect != "mongodb":
        try:
            cursor = conn.cursor()
            sql = _sample_sql(dialect, table.name, column.name, MAX_SAMPLE_VALUES)
            cursor.execute(sql)
            rows = cursor.fetchall() or []
            raw_values: List[str] = []
            for row in rows:
                v = row[0] if isinstance(row, (tuple, list)) else row
                if v is None:
                    continue
                raw_values.append(str(v))
            sample_values = tuple(raw_values[:MAX_SAMPLE_VALUES])
            sample_count = len(rows)
            if sample_count == 0:
                notes.append(
                    "empty table — semantic embedding will rely on metadata only"
                )
        except Exception as e:  # noqa: BLE001 — explicit surfacing per the honesty invariant
            notes.append(f"sampling failed: {type(e).__name__}: {e}")
    else:
        # Mongo: caller passes a Mongo-aware conn with a ``sample`` method.
        try:
            sampler = getattr(conn, "sample", None)
            if callable(sampler):
                raw = sampler(table.name, column.name, MAX_SAMPLE_VALUES)
                sample_values = tuple(str(v) for v in raw if v is not None)
                sample_count = len(sample_values)
                if sample_count == 0:
                    notes.append("empty collection — embedding will rely on metadata only")
            else:
                notes.append("mongo connection has no .sample() helper")
        except Exception as e:  # noqa: BLE001
            notes.append(f"mongo sampling failed: {type(e).__name__}: {e}")

    usages, usage_notes = lookup_column_usage(table.name, column.name)
    notes.extend(usage_notes)

    return ColumnContext(
        column=column,
        table_name=table.name,
        sample_values=sample_values,
        sample_count=sample_count,
        codebase_usage=usages,
        confidence_notes=tuple(notes),
    )


def extract(
    schema: SchemaSpec, conn: Optional[DBConnection]
) -> Tuple[ColumnContext, ...]:
    """Extract per-column context for every column in ``schema``.

    If ``conn`` is None we still emit a ColumnContext per column (with empty
    sample_values and a ``no_connection`` note). This is intentional: D3 in
    PR B can run against a customer who hasn't yet wired up read replicas.
    """
    out: List[ColumnContext] = []
    if conn is not None:
        _verify_read_only(conn, schema.dialect)
    for table in schema.tables:
        for col in table.columns:
            if conn is None:
                usages, usage_notes = lookup_column_usage(table.name, col.name)
                out.append(
                    ColumnContext(
                        column=col,
                        table_name=table.name,
                        sample_values=(),
                        sample_count=0,
                        codebase_usage=usages,
                        confidence_notes=("no_db_connection",) + usage_notes,
                    )
                )
            else:
                out.append(_extract_column(conn, schema.dialect, table, col))
    return tuple(out)


__all__ = [
    "MAX_SAMPLE_VALUES",
    "ReadOnlyError",
    "DBConnection",
    "extract",
]
