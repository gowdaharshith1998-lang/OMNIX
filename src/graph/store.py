"""SQLite-backed graph storage for OMNIX."""

from __future__ import annotations

import json
import sqlite3
import time
from collections.abc import Iterator
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
            CREATE INDEX IF NOT EXISTS idx_nodes_file_path ON nodes(file_path);
            CREATE INDEX IF NOT EXISTS idx_edges_source_id ON edges(source_id);
            CREATE INDEX IF NOT EXISTS idx_edges_target ON edges(target_id);
            CREATE INDEX IF NOT EXISTS idx_edges_source_rel ON edges(source_id, relationship);
            """
        )
        # Legacy name; superseded by idx_edges_source_id (keeps existing DBs deduped).
        self._conn.execute("DROP INDEX IF EXISTS idx_edges_source")
        _evo_schema.apply_evolution_schema(self._conn)
        self._conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS meta (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS file_hashes (
                file_path TEXT PRIMARY KEY,
                sha256 TEXT NOT NULL,
                last_modified REAL NOT NULL,
                last_parsed_at REAL NOT NULL,
                node_count INTEGER NOT NULL,
                edge_count INTEGER NOT NULL
            );
            """
        )
        self._conn.commit()

    def reset(self) -> None:
        self._conn.executescript(
            "DELETE FROM skip_summary WHERE 1;"
            "DELETE FROM edges; DELETE FROM nodes;"
        )
        self._conn.commit()

    def get_meta(self, key: str) -> str | None:
        r = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return str(r[0]) if r else None

    def set_meta(self, key: str, value: str) -> None:
        self._conn.execute(
            "INSERT OR REPLACE INTO meta (key, value) VALUES (?, ?)",
            (key, value),
        )

    def get_file_hash_row(self, file_path: str) -> tuple[str, float, float, int, int] | None:
        r = self._conn.execute(
            "SELECT sha256, last_modified, last_parsed_at, node_count, edge_count "
            "FROM file_hashes WHERE file_path = ?",
            (file_path,),
        ).fetchone()
        if not r:
            return None
        return (
            str(r[0]),
            float(r[1]),
            float(r[2]),
            int(r[3]),
            int(r[4]),
        )

    def set_file_hash(
        self,
        file_path: str,
        sha256: str,
        last_modified: float,
        *,
        node_count: int,
        edge_count: int,
    ) -> None:
        t = time.time()
        self._conn.execute(
            """
            INSERT OR REPLACE INTO file_hashes
            (file_path, sha256, last_modified, last_parsed_at, node_count, edge_count)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (file_path, sha256, last_modified, t, node_count, edge_count),
        )

    def delete_file_hash(self, file_path: str) -> None:
        self._conn.execute("DELETE FROM file_hashes WHERE file_path = ?", (file_path,))

    def all_file_hash_paths(self) -> list[str]:
        cur = self._conn.execute("SELECT file_path FROM file_hashes")
        return [str(x[0]) for x in cur.fetchall()]

    def clear_file_hashes(self) -> None:
        self._conn.execute("DELETE FROM file_hashes")

    def delete_graph_rows_for_file_path(self, file_path: str) -> None:
        """Remove nodes (and their edges) whose ``file_path`` is *file_path*."""
        c = self._conn
        c.execute("DELETE FROM edges WHERE source_id IN (SELECT id FROM nodes WHERE file_path = ?) OR target_id IN (SELECT id FROM nodes WHERE file_path = ?)", (file_path, file_path))  # noqa: E501
        c.execute("DELETE FROM nodes WHERE file_path = ?", (file_path,))

    def full_invalidate_ingest_cache(
        self, *, also_clear_evolution_grammar: bool = True
    ) -> None:
        """Wipe graph + per-file cache + skip summary. Optionally reset grammar_profile aggregates."""
        self._conn.executescript(
            "DELETE FROM skip_summary WHERE 1;"
            "DELETE FROM file_hashes WHERE 1;"
            "DELETE FROM edges; DELETE FROM nodes;"
        )
        if also_clear_evolution_grammar:
            self._conn.execute("DELETE FROM grammar_profile")
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

    def iter_all_nodes(self) -> Iterator[NodeRow]:
        for r in self._conn.execute("SELECT * FROM nodes"):
            yield _row_to_node(r)

    def iter_all_edges(self) -> Iterator[EdgeRow]:
        for r in self._conn.execute("SELECT * FROM edges"):
            yield _row_to_edge(r)

    def iter_nodes_by_file(self, file_path: str) -> Iterator[NodeRow]:
        for r in self._conn.execute(
            "SELECT * FROM nodes WHERE file_path = ?", (file_path,)
        ):
            yield _row_to_node(r)

    def get_all_nodes(self) -> list[NodeRow]:
        return list(self.iter_all_nodes())

    def get_all_edges(self) -> list[EdgeRow]:
        return list(self.iter_all_edges())

    def count_call_edges_for_file(self, rel: str) -> int:
        """Count CALLS edges with ``source_id`` matching Python's ``str.startswith(rel)``."""
        row = self._conn.execute(
            """
            SELECT COUNT(*) FROM edges
            WHERE relationship = 'CALLS'
              AND length(source_id) >= length(?)
              AND substr(source_id, 1, length(?)) = ?
            """,
            (rel, rel, rel),
        ).fetchone()
        return int(row[0]) if row else 0

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

    def count_nodes(self) -> int:
        return self.node_count()

    def count_edges(self) -> int:
        return self.edge_count()

    def commit(self) -> None:
        self._conn.commit()

    def begin_batch(self) -> None:
        """Start a single DEFERRED transaction (batch of graph writes)."""
        if not self._open_batch:
            # End any implicit transaction from standalone operations (e.g. set_file_hash
            # on an empty/skip path) so BEGIN does not nest.
            self._conn.commit()
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
