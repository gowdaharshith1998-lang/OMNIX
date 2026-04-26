"""SQLite-backed graph storage for OMNIX."""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass
from typing import Any

import src.parser.evolution_schema as _evo_schema


@dataclass
class NodeRow:
    id: str
    name: str
    type: str
    file_path: str | None
    start_line: int | None
    end_line: int | None
    complexity: int
    metadata: dict[str, Any] | None


@dataclass
class EdgeRow:
    id: int
    source_id: str
    target_id: str
    relationship: str
    metadata: dict[str, Any] | None


class GraphStore:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._conn = sqlite3.connect(db_path, isolation_level="DEFERRED", check_same_thread=False)  # noqa: E501
        self._conn.row_factory = sqlite3.Row
        self._open_batch: bool = False
        self._ensure_schema()
        jm = self._conn.execute("PRAGMA journal_mode").fetchone()
        if not jm or (jm[0] or "").upper() != "WAL":
            self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA synchronous=NORMAL")

    def _ensure_schema(self) -> None:
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS nodes (
                id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                type TEXT NOT NULL,
                file_path TEXT,
                start_line INTEGER,
                end_line INTEGER,
                complexity INTEGER DEFAULT 0,
                metadata TEXT
            );
            CREATE TABLE IF NOT EXISTS edges (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                source_id TEXT NOT NULL,
                target_id TEXT NOT NULL,
                relationship TEXT NOT NULL,
                metadata TEXT,
                FOREIGN KEY (source_id) REFERENCES nodes(id),
                FOREIGN KEY (target_id) REFERENCES nodes(id)
            );
            CREATE INDEX IF NOT EXISTS idx_edges_source ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
            """
        )
        _evo_schema.apply_evolution_schema(self._conn)
        self._conn.commit()

    def reset(self) -> None:
        self._conn.executescript(
            "DELETE FROM skip_summary WHERE 1;"
            "DELETE FROM edges; DELETE FROM nodes;"
        )
        self._conn.commit()

    def sqlite_connection(self) -> sqlite3.Connection:
        """Shared connection (graph + evolution tables in one file)."""
        return self._conn

    def close(self) -> None:
        self._conn.close()

    def add_node(
        self,
        id: str,
        name: str,
        type: str,
        file_path: str | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        complexity: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        meta_json = json.dumps(metadata) if metadata else None
        self._conn.execute(
            """
            INSERT OR REPLACE INTO nodes
            (id, name, type, file_path, start_line, end_line, complexity, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (id, name, type, file_path, start_line, end_line, complexity, meta_json),
        )

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relationship: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        meta_json = json.dumps(metadata, sort_keys=True) if metadata else None
        cur = self._conn.execute(
            """
            SELECT 1 FROM edges
            WHERE source_id = ? AND target_id = ? AND relationship = ?
              AND IFNULL(metadata, '') = IFNULL(?, '')
            LIMIT 1
            """,
            (source_id, target_id, relationship, meta_json),
        )
        if cur.fetchone():
            return False
        self._conn.execute(
            """
            INSERT INTO edges (source_id, target_id, relationship, metadata)
            VALUES (?, ?, ?, ?)
            """,
            (source_id, target_id, relationship, meta_json),
        )
        return True

    def get_all_nodes(self) -> list[NodeRow]:
        rows = self._conn.execute("SELECT * FROM nodes").fetchall()
        return [_row_to_node(r) for r in rows]

    def get_all_edges(self) -> list[EdgeRow]:
        rows = self._conn.execute("SELECT * FROM edges").fetchall()
        return [_row_to_edge(r) for r in rows]

    def get_neighbors(self, node_id: str) -> list[NodeRow]:
        rows = self._conn.execute(
            """
            SELECT DISTINCT n.* FROM nodes n
            WHERE n.id IN (
                SELECT target_id FROM edges WHERE source_id = ?
                UNION
                SELECT source_id FROM edges WHERE target_id = ?
            )
            """,
            (node_id, node_id),
        ).fetchall()
        return [_row_to_node(r) for r in rows]

    def search(self, query: str, limit: int = 200) -> list[NodeRow]:
        q = f"%{query}%"
        rows = self._conn.execute(
            """
            SELECT * FROM nodes
            WHERE name LIKE ? OR id LIKE ? OR file_path LIKE ?
            LIMIT ?
            """,
            (q, q, q, limit),
        ).fetchall()
        return [_row_to_node(r) for r in rows]

    def node_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM nodes").fetchone()
        return int(row[0]) if row else 0

    def edge_count(self) -> int:
        row = self._conn.execute("SELECT COUNT(*) FROM edges").fetchone()
        return int(row[0]) if row else 0

    def commit(self) -> None:
        self._conn.commit()

    def begin_batch(self) -> None:
        """Start a single DEFERRED transaction (batch of graph writes)."""
        if not self._open_batch:
            self._conn.execute("BEGIN")
            self._open_batch = True

    def commit_batch(self) -> None:
        """Commit the current batch transaction (no-op if no batch open)."""
        if not self._open_batch:
            return
        try:
            self._conn.commit()
        except (OSError, ValueError):
            self._conn.rollback()
            self._open_batch = False
            raise
        self._open_batch = False

    def rollback_batch(self) -> None:
        if self._open_batch:
            self._conn.rollback()
            self._open_batch = False

    def import_graph_snapshot(
        self, nodes: list[dict[str, Any]], edges: list[dict[str, Any]]
    ) -> None:
        """
        Apply nodes and edges from a worker :class:`MemoryGraphStore` dump.
        Caller must hold an open batch (``begin_batch``) for transactional grouping.
        """
        if not nodes and not edges:
            return
        nparams = [
            (
                r["id"],
                r["name"],
                r["type"],
                r.get("file_path"),
                r.get("start_line"),
                r.get("end_line"),
                r.get("complexity", 0),
                json.dumps(r["metadata"]) if r.get("metadata") else None,
            )
            for r in nodes
        ]
        eparams = [
            (
                e["source_id"],
                e["target_id"],
                e["relationship"],
                json.dumps(e["metadata"], sort_keys=True) if e.get("metadata") else None,
            )
            for e in edges
        ]
        if nparams:
            self._conn.executemany(
                """
                INSERT OR REPLACE INTO nodes
                (id, name, type, file_path, start_line, end_line, complexity, metadata)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                nparams,
            )
        if eparams:
            self._conn.executemany(
                """
                INSERT INTO edges (source_id, target_id, relationship, metadata)
                VALUES (?, ?, ?, ?)
                """,
                eparams,
            )

    def replace_skip_summary(
        self, rows: list[tuple[str, int, int, str, str | None]]
    ) -> None:
        """Replace ``skip_summary`` contents (analyze ingest; one run per DB)."""
        cur = self._conn.cursor()
        cur.execute("DELETE FROM skip_summary")
        if rows:
            cur.executemany(
                """
                INSERT INTO skip_summary(extension, files, loc, reason, suggested_install)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )
        self._conn.commit()


def _row_to_node(r: sqlite3.Row) -> NodeRow:
    meta = r["metadata"]
    return NodeRow(
        id=r["id"],
        name=r["name"],
        type=r["type"],
        file_path=r["file_path"],
        start_line=r["start_line"],
        end_line=r["end_line"],
        complexity=r["complexity"] or 0,
        metadata=json.loads(meta) if meta else None,
    )


def _row_to_edge(r: sqlite3.Row) -> EdgeRow:
    meta = r["metadata"]
    return EdgeRow(
        id=r["id"],
        source_id=r["source_id"],
        target_id=r["target_id"],
        relationship=r["relationship"],
        metadata=json.loads(meta) if meta else None,
    )
