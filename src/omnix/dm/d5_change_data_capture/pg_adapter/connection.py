"""psycopg2 logical-replication connection helpers."""

from __future__ import annotations

from typing import Any, Iterable, Optional


def open_replication_connection(dsn: str):
    """Open a psycopg2 connection with ``replication='database'``. Returns a
    :class:`psycopg2.extras.LogicalReplicationConnection`."""
    import psycopg2
    from psycopg2.extras import LogicalReplicationConnection

    return psycopg2.connect(
        dsn,
        connection_factory=LogicalReplicationConnection,
    )


def ensure_publication(conn: Any, publication_name: str, tables: Optional[Iterable[str]] = None) -> None:
    """Idempotently create or update a publication."""
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM pg_publication WHERE pubname = %s", (publication_name,)
    )
    exists = cur.fetchone() is not None
    if not exists:
        if tables:
            tbl_list = ", ".join(f'"{t}"' for t in tables if '"' not in t and "\x00" not in t)
            cur.execute(f"CREATE PUBLICATION {_quote(publication_name)} FOR TABLE {tbl_list}")
        else:
            cur.execute(f"CREATE PUBLICATION {_quote(publication_name)} FOR ALL TABLES")
    conn.commit() if hasattr(conn, "commit") else None


def ensure_slot(conn: Any, slot_name: str, output_plugin: str = "pgoutput") -> None:
    """Idempotently create a logical replication slot."""
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM pg_replication_slots WHERE slot_name = %s", (slot_name,)
    )
    exists = cur.fetchone() is not None
    if not exists:
        # Replication-connection API: pg_create_logical_replication_slot
        cur.execute(
            "SELECT pg_create_logical_replication_slot(%s, %s)",
            (slot_name, output_plugin),
        )


def _quote(name: str) -> str:
    if '"' in name or "\x00" in name:
        raise ValueError(f"unsafe identifier {name!r}")
    return f'"{name}"'


__all__ = [
    "open_replication_connection",
    "ensure_publication",
    "ensure_slot",
]
