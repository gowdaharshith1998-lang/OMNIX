"""Tests for `omnix grammar status` / :mod:`omnix.parser.cli` (read-only)."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture
def synthetic_db(tmp_path: Path) -> Path:
    """Minimal `.omnix/omnix.db` with known grammar evolution rows."""
    omnix_dir = tmp_path / ".omnix"
    omnix_dir.mkdir()
    db_path = omnix_dir / "omnix.db"

    conn = sqlite3.connect(str(db_path))
    from omnix.parser.evolution_schema import apply_evolution_schema

    apply_evolution_schema(conn)
    conn.execute(
        "INSERT INTO grammar_profile (grammar_name, first_seen_at, total_files_parsed, "
        "total_quality_score) VALUES (?, ?, ?, ?), (?, ?, ?, ?)",
        (
            "python",
            "2026-01-01T00:00:00Z",
            10,
            6.83,
            "rust",
            "2026-01-02T00:00:00Z",
            0,
            0.0,
        ),
    )
    conn.execute(
        "INSERT INTO query_pattern (grammar_name, node_type, role, hit_count, miss_count, "
        "is_active, added_at, added_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("python", "call", "callee", 1, 0, 1, "2026-01-01T00:00:00Z", "builtin_hint"),
    )
    conn.execute(
        "INSERT INTO pattern_mutation (grammar_name, mutation_kind, pattern_id, reason, "
        "observed_at, receipt_path, sig_path) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "python",
            "promote",
            1,
            "test",
            "2026-05-01T12:00:00Z",
            "/tmp/ev_r.json",
            "/tmp/ev_r.sig",
        ),
    )
    conn.execute(
        "INSERT INTO unknown_extensions (extension, first_seen_at) VALUES (?, ?), (?, ?)",
        (".foo", "2026-01-01T00:00:00Z", ".bar", "2026-01-02T00:00:00Z"),
    )
    conn.commit()
    conn.close()
    return db_path


def _run_cli(argv: list[str]) -> subprocess.CompletedProcess[str]:
    env = {**os.environ, "PYTHONPATH": str(REPO_ROOT)}
    return subprocess.run(
        [sys.executable, "-m", "omnix.parser.cli", *argv],
        cwd=str(REPO_ROOT),
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )


def test_status_prints_table(synthetic_db: Path) -> None:
    r = _run_cli(["status", "--db", str(synthetic_db)])
    assert r.returncode == 0
    assert "python" in r.stdout
    assert "Grammar" in r.stdout
    assert "Avg quality" in r.stdout
    assert "0.683" in r.stdout or "683" in r.stdout


def test_status_json_flag(synthetic_db: Path) -> None:
    r = _run_cli(["status", "--db", str(synthetic_db), "--json"])
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert "grammars" in data
    assert isinstance(data["grammars"], list)
    assert data["db_path"]
    assert "unknown_extensions" in data
    assert "llm_fallback" in data


def test_status_grammar_filter(synthetic_db: Path) -> None:
    r = _run_cli(
        ["status", "--db", str(synthetic_db), "--grammar", "python", "--json"],
    )
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert len(data["grammars"]) == 1
    assert data["grammars"][0]["grammar_name"] == "python"


def test_status_no_db_returns_1(tmp_path: Path) -> None:
    r = _run_cli(["status", "--db", str(tmp_path / "nonexistent.db")])
    assert r.returncode == 1


def test_status_empty_db_returns_2(tmp_path: Path) -> None:
    db_path = tmp_path / "empty.db"
    conn = sqlite3.connect(str(db_path))
    from omnix.parser.evolution_schema import apply_evolution_schema

    apply_evolution_schema(conn)
    conn.commit()
    conn.close()

    r = _run_cli(["status", "--db", str(db_path)])
    assert r.returncode == 2


def test_status_readonly_does_not_mutate(synthetic_db: Path) -> None:
    mtime_before = synthetic_db.stat().st_mtime_ns
    subprocess.run(
        [sys.executable, "-m", "omnix.parser.cli", "status", "--db", str(synthetic_db)],
        cwd=str(REPO_ROOT),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )
    mtime_after = synthetic_db.stat().st_mtime_ns
    assert mtime_before == mtime_after


def test_status_walks_up_from_cwd(synthetic_db: Path) -> None:
    parent = synthetic_db.parent.parent
    sub = parent / "deep" / "nested" / "dir"
    sub.mkdir(parents=True)

    r = subprocess.run(
        [sys.executable, "-m", "omnix.parser.cli", "status", "--json"],
        cwd=str(sub),
        env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    data = json.loads(r.stdout)
    assert Path(data["db_path"]).resolve() == synthetic_db.resolve()
