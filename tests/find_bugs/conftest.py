"""Empty SQLite graph (schema) for find-bugs tests."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest


def _empty_schema() -> str:
    return """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
    file_path TEXT, start_line INTEGER, end_line INTEGER,
    complexity INTEGER DEFAULT 0, metadata TEXT
);
CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL, target_id TEXT NOT NULL,
    relationship TEXT NOT NULL, metadata TEXT
);
"""


@pytest.fixture
def empty_graph_db_path(tmp_path: Path) -> str:
    p = tmp_path / "omnix.db"
    c = sqlite3.connect(p)
    c.executescript(_empty_schema())
    c.close()
    return str(p)
