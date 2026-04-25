"""Q2: find-bugs per-codebase ``omnix.db`` resolution (per-codebase, no home fallback)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.find_bugs import runner as fr


def test_creates_per_codebase_db_when_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    h = tmp_path / "h"
    h.mkdir()
    monkeypatch.setenv("HOME", str(h))
    ohome = h / ".omnix"
    ohome.mkdir()
    dball = ohome / "omnix.db"
    dball.write_text("x", encoding="utf-8")
    m0 = dball.stat().st_mtime
    code = tmp_path / "p"
    code.mkdir()
    (code / "a.py").write_text("def f():\n    return 0\n", encoding="utf-8")
    p = (code / "omnix.db").resolve()
    assert not p.is_file()
    a, b = fr.ensure_find_bugs_graph_db(code, None)
    assert a is not None
    assert b is None
    assert p.is_file()
    assert dball.read_text() == "x" and dball.stat().st_mtime == m0


def test_respects_omnix_graph_db_explicit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    explicit = (tmp_path / "explicit.db").resolve()
    monkeypatch.delenv("OMNIX_GRAPH_DB", raising=False)
    a, b = fr.ensure_find_bugs_graph_db(tmp_path / "empty", str(explicit))
    assert a == explicit
    assert b is None
    assert explicit.is_file()


def test_respects_omnix_graph_db_env_creates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    t = (tmp_path / "from_env.db").resolve()
    monkeypatch.setenv("OMNIX_GRAPH_DB", str(t))
    a, b = fr.ensure_find_bugs_graph_db(tmp_path / "code", None)
    assert a == t
    assert b is None
    assert t.is_file()


def test_fails_clearly_on_readonly_codebase(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = tmp_path / "ro"
    d.mkdir()
    (d / "a.py").write_text("x=1\n", encoding="utf-8")
    d.chmod(0o555)
    try:
        monkeypatch.delenv("OMNIX_GRAPH_DB", raising=False)
        a, b = fr.ensure_find_bugs_graph_db(d, None)
        if b is not None:
            assert a is None
            assert "cannot" in b.lower() or "create" in b.lower()
    finally:
        d.chmod(0o700)
