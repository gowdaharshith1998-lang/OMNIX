"""Incremental enrichment cache keyed by node source hashes."""

from __future__ import annotations

from omnix.enrich.common import utc_now_iso
from omnix.graph.store import GraphStore


class EnrichmentCache:
    def __init__(self, graph_store: GraphStore) -> None:
        self.graph_store = graph_store
        conn = graph_store.sqlite_connection()
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS enrichment_cache (
                node_id TEXT NOT NULL,
                pass_name TEXT NOT NULL,
                source_sha256 TEXT NOT NULL,
                enriched_at TEXT NOT NULL,
                PRIMARY KEY (node_id, pass_name)
            );
            CREATE INDEX IF NOT EXISTS idx_enrichment_cache_pass
                ON enrichment_cache(pass_name, node_id);
            """
        )
        graph_store.commit()

    def is_stale(self, node_id: str, pass_name: str, source_sha256: str) -> bool:
        row = self.graph_store.sqlite_connection().execute(
            """
            SELECT source_sha256 FROM enrichment_cache
            WHERE node_id = ? AND pass_name = ?
            """,
            (node_id, pass_name),
        ).fetchone()
        return row is None or str(row[0]) != source_sha256

    def mark_enriched(self, node_id: str, pass_name: str, source_sha256: str) -> None:
        self.graph_store.sqlite_connection().execute(
            """
            INSERT OR REPLACE INTO enrichment_cache
                (node_id, pass_name, source_sha256, enriched_at)
            VALUES (?, ?, ?, ?)
            """,
            (node_id, pass_name, source_sha256, utc_now_iso()),
        )
        self.graph_store.commit()
