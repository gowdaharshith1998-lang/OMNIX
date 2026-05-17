"""Phase 13.5: aggregate skip reporting, skip_summary table, strict / threshold exits."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from omnix.graph.store import GraphStore
from omnix.parser import grammar_detect as gd
from omnix.parser import ingest_dispatch as ind
from omnix.parser.skip_tracking import exit_code_for_skips, format_skip_banner


def test_no_grammar_skip_reported_in_banner(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = gd.try_load_language_for_grammar

    def _fake(g: str):  # noqa: ANN001
        if g == "go":
            return None
        return real(g)

    monkeypatch.setattr(gd, "try_load_language_for_grammar", _fake)
    # Workers run in child processes; monkeypatch only applies in-process (workers=1).
    monkeypatch.setenv("OMNIX_INGEST_WORKERS", "1")
    (tmp_path / "main.go").write_text("package main\nfunc main() {}\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    store = GraphStore(str(tmp_path / "t.db"))
    tot = ind.ingest_unified_codebase(str(tmp_path), store, parse_mode="generic")
    store.close()
    assert tot.skip.has_no_grammar is True
    banner = format_skip_banner(tot.skip)
    assert banner is not None
    assert ".go" in banner
    assert "tree-sitter-go" in banner


def test_unknown_extension_skip_reported(
    tmp_path: Path,
) -> None:
    (tmp_path / "weird.xyz").write_text("hello\nworld\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("y = 2\n", encoding="utf-8")
    store = GraphStore(str(tmp_path / "u.db"))
    tot = ind.ingest_unified_codebase(str(tmp_path), store, parse_mode="generic")
    store.close()
    banner = format_skip_banner(tot.skip)
    assert banner is not None
    assert ".xyz" in banner
    assert "no grammar mapped" in banner


def test_skip_summary_table_populated(tmp_path: Path) -> None:
    (tmp_path / "weird.xyz").write_text("a\n", encoding="utf-8")
    (tmp_path / "ok.py").write_text("z = 3\n", encoding="utf-8")
    dbp = tmp_path / "ss.db"
    store = GraphStore(str(dbp))
    _ = ind.ingest_unified_codebase(str(tmp_path), store, parse_mode="generic")
    store.close()
    con = sqlite3.connect(str(dbp))
    rows = con.execute(
        "SELECT extension, files, reason FROM skip_summary ORDER BY extension"
    ).fetchall()
    con.close()
    assert any(r[0] == ".xyz" and r[2] == "unknown_extension" for r in rows)


def test_strict_mode_exits_2_on_no_grammar(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    real = gd.try_load_language_for_grammar

    def _fake(g: str):  # noqa: ANN001
        if g == "go":
            return None
        return real(g)

    monkeypatch.setattr(gd, "try_load_language_for_grammar", _fake)
    (tmp_path / "x.go").write_text("package main\n", encoding="utf-8")
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    store = GraphStore(str(tmp_path / "st.db"))
    tot = ind.ingest_unified_codebase(str(tmp_path), store, parse_mode="generic")
    store.close()
    rc = exit_code_for_skips(strict=True, ratio_threshold=0.5, agg=tot.skip)
    assert rc == 2


def test_skip_threshold_flag_respects_value(tmp_path: Path) -> None:
    for i in range(20):
        (tmp_path / f"u{i}.xyz").write_text("line\n" * 100, encoding="utf-8")
    (tmp_path / "only.py").write_text("a = 1\n", encoding="utf-8")
    store = GraphStore(str(tmp_path / "th.db"))
    tot = ind.ingest_unified_codebase(str(tmp_path), store, parse_mode="generic")
    store.close()
    assert tot.skip.has_no_grammar is False
    rc_loose = exit_code_for_skips(strict=False, ratio_threshold=1.0, agg=tot.skip)
    assert rc_loose == 0
    rc_tight = exit_code_for_skips(strict=False, ratio_threshold=0.01, agg=tot.skip)
    assert rc_tight == 2
