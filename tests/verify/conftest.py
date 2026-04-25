"""Test fixtures: minimal SQLite graph (schema only, read-only for verify)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

_SCHEMA = """
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
def empty_graph_db(tmp_path: Path) -> Path:
    p = tmp_path / "g.db"
    c = sqlite3.connect(p)
    c.executescript(_SCHEMA)
    c.close()
    return p


@pytest.fixture
def graph_db_for_runner(
    empty_graph_db: Path,
) -> str:
    """Prefer repo omnix.db after `analyze`, else a minimal empty graph."""
    _repo = Path(__file__).resolve().parents[2]
    o = _repo / "omnix.db"
    if o.is_file():
        return str(o)
    return str(empty_graph_db)
