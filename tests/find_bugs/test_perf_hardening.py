"""Slice 18d step 5 — perf bounds (RSS cap, per-fn timeout, total scan budget)."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

pytest.importorskip("hypothesis", reason="hypothesis required")

from find_bugs import runner


def _empty_graph(tmp_path: Path) -> str:
    p = tmp_path / "omnix.db"
    schema = """
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
    c = sqlite3.connect(p)
    c.executescript(schema)
    c.close()
    return str(p)


def test_memory_pathology_finding_on_large_bytes_alloc(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".omnix" / "receipts").mkdir(parents=True, exist_ok=True)
    hog = tmp_path / "hog.py"
    hog.write_text(
        textwrap.dedent(
            """
            def alloc_big(n: int) -> bytes:
                _ = n
                return bytes(350_000_000)
            """
        ).lstrip(),
        encoding="utf-8",
    )
    ex, _out, bundle = runner.run_find_bugs(
        str(tmp_path),
        examples=8,
        top=10,
        json_mode=True,
        no_bundle=True,
        graph_db=_empty_graph(tmp_path),
        rss_cap_mb=256,
        per_fn_timeout_s=25.0,
        total_timeout_s=120.0,
    )
    assert ex in (0, 1)
    assert bundle is not None
    kinds = {
        str(r.get("kind"))
        for r in (bundle.get("findings") or [])
        if isinstance(r, dict)
    }
    assert "memory_pathology" in kinds


def test_timeout_pathology_finding_on_infinite_loop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".omnix" / "receipts").mkdir(parents=True, exist_ok=True)
    lp = tmp_path / "loop.py"
    lp.write_text(
        textwrap.dedent(
            """
            def spins(x: int) -> int:
                while True:
                    x += 1
                return x
            """
        ).lstrip(),
        encoding="utf-8",
    )
    ex, _out, bundle = runner.run_find_bugs(
        str(tmp_path),
        examples=3,
        top=10,
        json_mode=True,
        no_bundle=True,
        graph_db=_empty_graph(tmp_path),
        turboscan=False,
        filesystem_hygiene=False,
        per_fn_timeout_s=5.0,
        total_timeout_s=60.0,
    )
    assert ex in (0, 1)
    assert bundle is not None
    kinds = {
        str(r.get("kind"))
        for r in (bundle.get("findings") or [])
        if isinstance(r, dict)
    }
    assert "timeout_pathology" in kinds


def test_total_scan_timeout_legacy_partial_results(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".omnix" / "receipts").mkdir(parents=True, exist_ok=True)
    for i in range(3):
        (tmp_path / f"slow_{i}.py").write_text(
            textwrap.dedent(
                f"""
                def slow_{i}(x: int) -> int:
                    while True:
                        x += 1
                    return x
                """
            ).lstrip(),
            encoding="utf-8",
        )
    runner.run_find_bugs(
        str(tmp_path),
        examples=2,
        top=20,
        json_mode=True,
        no_bundle=True,
        graph_db=_empty_graph(tmp_path),
        turboscan=False,
        filesystem_hygiene=False,
        per_fn_timeout_s=4.0,
        total_timeout_s=6.0,
    )
    err = capsys.readouterr().err
    assert "total scan timeout" in err.lower()


def test_default_examples_cli_parser_is_5() -> None:
    from find_bugs.cli import _build_parser

    p = _build_parser()
    act = next(a for a in p._actions if getattr(a, "dest", None) == "examples")
    assert act.default == 5


def test_explicit_examples_25_still_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".omnix" / "receipts").mkdir(parents=True, exist_ok=True)
    (tmp_path / "trivial.py").write_text(
        "def safe(x: int) -> int:\n    return x + 1\n",
        encoding="utf-8",
    )
    ex, _out, bundle = runner.run_find_bugs(
        str(tmp_path),
        examples=25,
        json_mode=True,
        no_bundle=True,
        graph_db=_empty_graph(tmp_path),
        turboscan=False,
        filesystem_hygiene=False,
        per_fn_timeout_s=20.0,
        total_timeout_s=90.0,
    )
    assert ex in (0, 1)
    assert bundle is not None


def test_omnix_version_reports_module_version() -> None:
    repo = Path(__file__).resolve().parents[2]
    env = {**os.environ, "PYTHONPATH": f"{repo}{os.pathsep}{repo / 'src'}"}
    proc = subprocess.run(
        [sys.executable, "-m", "cli", "--version"],
        cwd=str(repo),
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    assert proc.returncode == 0
    assert "0.5.0" in proc.stdout
