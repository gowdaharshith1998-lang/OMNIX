"""Merkle-style incremental analyze (14b-3)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from omnix.graph.store import GraphStore
from omnix.omnix_version import __version__ as OMNIX_V
from omnix.parser import evolution
from omnix.parser import ingest_dispatch as ind
from omnix.parser.ingest_dispatch import quality_profile_fingerprint


def _n(db: Path) -> tuple[int, int]:
    c = sqlite3.connect(str(db))
    try:
        a = c.execute("SELECT COUNT(*) FROM nodes").fetchone()[0]
        b = c.execute("SELECT COUNT(*) FROM file_hashes").fetchone()[0]
        return (int(a), int(b))
    finally:
        c.close()


def test_unchanged_file_skipped_on_second_run(tmp_path: Path) -> None:
    (tmp_path / "m.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    dbp = tmp_path / "x.db"
    evolution.begin_evolution_run()
    s = GraphStore(str(dbp))
    t1 = ind.ingest_unified_codebase(str(tmp_path), s, parse_mode="generic", force=False)
    s.close()
    n1, f1 = _n(dbp)
    assert f1 > 0
    assert t1.cached == 0
    evolution.begin_evolution_run()
    s2 = GraphStore(str(dbp))
    t2 = ind.ingest_unified_codebase(str(tmp_path), s2, parse_mode="generic", force=False)
    s2.close()
    n2, f2 = _n(dbp)
    assert n1 == n2
    assert f1 == f2
    assert t2.cached >= 1


def test_changed_file_reparsed_on_second_run(tmp_path: Path) -> None:
    f = tmp_path / "c.py"
    f.write_text("x = 1\n", encoding="utf-8")
    dbp = tmp_path / "c.db"
    evolution.begin_evolution_run()
    s = GraphStore(str(dbp))
    _ = ind.ingest_unified_codebase(str(tmp_path), s, parse_mode="generic")
    s.close()
    f.write_text("x = 1\ny = 2\n", encoding="utf-8")
    evolution.begin_evolution_run()
    s2 = GraphStore(str(dbp))
    t2 = ind.ingest_unified_codebase(str(tmp_path), s2, parse_mode="generic")
    s2.close()
    assert t2.cached == 0


def test_removed_file_purged_from_db(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    a.write_text("r = 1\n", encoding="utf-8")
    (tmp_path / "b.py").write_text("s = 2\n", encoding="utf-8")
    dbp = tmp_path / "r.db"
    evolution.begin_evolution_run()
    s = GraphStore(str(dbp))
    _ = ind.ingest_unified_codebase(str(tmp_path), s, parse_mode="generic")
    s.close()
    a.unlink()
    evolution.begin_evolution_run()
    s2 = GraphStore(str(dbp))
    _ = ind.ingest_unified_codebase(str(tmp_path), s2, parse_mode="generic")
    s2.close()
    c = sqlite3.connect(str(dbp))
    try:
        n_a = c.execute("SELECT COUNT(*) FROM nodes WHERE file_path = 'a.py'").fetchone()[0]
        fh = c.execute(
            "SELECT 1 FROM file_hashes WHERE file_path = 'a.py'"
        ).fetchone()
    finally:
        c.close()
    assert int(n_a) == 0
    assert fh is None


def test_force_flag_bypasses_cache(tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text("a = 1\n", encoding="utf-8")
    dbp = tmp_path / "f.db"
    evolution.begin_evolution_run()
    s = GraphStore(str(dbp))
    t1 = ind.ingest_unified_codebase(str(tmp_path), s, parse_mode="generic", force=False)
    s.close()
    assert t1.cached == 0
    evolution.begin_evolution_run()
    s2 = GraphStore(str(dbp))
    t2 = ind.ingest_unified_codebase(str(tmp_path), s2, parse_mode="generic", force=True)
    s2.close()
    assert t2.cached == 0


def test_profile_change_invalidates_cache(
    tmp_path: Path, capsys: pytest.CaptureFixture
) -> None:
    (tmp_path / "p.py").write_text("z = 1\n", encoding="utf-8")
    dbp = tmp_path / "p.db"
    evolution.begin_evolution_run()
    s = GraphStore(str(dbp))
    _ = ind.ingest_unified_codebase(
        str(tmp_path), s, parse_mode="generic", omnix_version=OMNIX_V
    )
    s.close()
    fp0 = quality_profile_fingerprint()
    c = sqlite3.connect(str(dbp))
    c.execute("UPDATE meta SET value = ? WHERE key = 'profile_hash'", ("badhash",))
    c.commit()
    c.close()
    evolution.begin_evolution_run()
    s2 = GraphStore(str(dbp))
    _ = ind.ingest_unified_codebase(
        str(tmp_path), s2, parse_mode="generic", omnix_version=OMNIX_V
    )
    s2.close()
    err = capsys.readouterr().err
    assert "quality profiles" in err.lower() or "re-parsing" in err
    c2 = sqlite3.connect(str(dbp))
    try:
        p = c2.execute("SELECT value FROM meta WHERE key = 'profile_hash'").fetchone()
    finally:
        c2.close()
    assert p is not None
    assert p[0] != "badhash"
    assert p[0] == fp0


def test_version_bump_invalidates_cache(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    (tmp_path / "v.py").write_text("d = 1\n", encoding="utf-8")
    dbp = tmp_path / "v.db"
    evolution.begin_evolution_run()
    s = GraphStore(str(dbp))
    _ = ind.ingest_unified_codebase(str(tmp_path), s, parse_mode="generic", omnix_version="0.0.0-test")
    s.close()
    evolution.begin_evolution_run()
    s2 = GraphStore(str(dbp))
    _ = ind.ingest_unified_codebase(str(tmp_path), s2, parse_mode="generic", omnix_version=OMNIX_V)
    s2.close()
    err = capsys.readouterr().err
    assert "upgraded" in err or "0.0.0-test" in err


def test_meta_schema_version_persisted(tmp_path: Path) -> None:
    (tmp_path / "q.py").write_text("e = 1\n", encoding="utf-8")
    dbp = tmp_path / "m.db"
    evolution.begin_evolution_run()
    s = GraphStore(str(dbp))
    _ = ind.ingest_unified_codebase(str(tmp_path), s, parse_mode="generic")
    s.close()
    c = sqlite3.connect(str(dbp))
    try:
        v = c.execute("SELECT value FROM meta WHERE key = 'schema_version'").fetchone()
        o = c.execute("SELECT value FROM meta WHERE key = 'omnix_version'").fetchone()
    finally:
        c.close()
    assert v is not None
    assert v[0] == "3"
    assert o is not None
    assert o[0] == OMNIX_V
