"""Idempotent migration for evolution / grammar learning (same file as graph DB)."""

from __future__ import annotations

import sqlite3


def apply_evolution_schema(conn: sqlite3.Connection) -> None:
    cur = conn.cursor()
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS grammar_profile (
            grammar_name TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL,
            total_files_parsed INTEGER NOT NULL DEFAULT 0,
            total_quality_score REAL NOT NULL DEFAULT 0.0
        );
        """
    )
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS query_pattern (
            id INTEGER PRIMARY KEY,
            grammar_name TEXT NOT NULL,
            node_type TEXT NOT NULL,
            role TEXT NOT NULL,
            hit_count INTEGER NOT NULL DEFAULT 0,
            miss_count INTEGER NOT NULL DEFAULT 0,
            is_active INTEGER NOT NULL DEFAULT 1,
            added_at TEXT NOT NULL,
            added_by TEXT NOT NULL
        );
        """
    )
    cur.executescript(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_query_pattern_grammar_noderole
        ON query_pattern(grammar_name, node_type, role);
        """
    )
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS pattern_mutation (
            id INTEGER PRIMARY KEY,
            grammar_name TEXT NOT NULL,
            mutation_kind TEXT NOT NULL,
            pattern_id INTEGER,
            reason TEXT NOT NULL,
            observed_at TEXT NOT NULL,
            receipt_path TEXT NOT NULL,
            sig_path TEXT NOT NULL
        );
        """
    )
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS unknown_extensions (
            extension TEXT PRIMARY KEY,
            first_seen_at TEXT NOT NULL
        );
        """
    )
    cur.executescript(
        """
        CREATE TABLE IF NOT EXISTS skip_summary (
            extension TEXT NOT NULL,
            files INTEGER NOT NULL,
            loc INTEGER NOT NULL,
            reason TEXT NOT NULL,
            suggested_install TEXT
        );
        """
    )
    cur.executescript(
        """
        CREATE INDEX IF NOT EXISTS idx_skip_summary_loc ON skip_summary(loc DESC);
        """
    )
    conn.commit()
