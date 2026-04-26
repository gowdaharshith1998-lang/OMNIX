"""Parallel ingest (Crack 2) correctness and batching."""

from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path
from unittest import mock

import pytest

from src.graph.store import GraphStore
from src.parser import evolution, ingest_dispatch as ind
from src.parser import ingest_dispatch as ingmod

FIXTURE = Path(__file__).parent / "fixtures" / "parallel_consistency"


def _reset_pool_hook() -> None:
    ingmod._LAST_PROCESS_POOL_MAX_WORKERS = None  # type: ignore[misc]


def _snapshot_graph(db: Path) -> tuple[int, int, list[tuple[str, float]]]:
    s = GraphStore(str(db))
    n = s.node_count()
    e = s.edge_count()
    qs: list[tuple[str, float]] = []
    s.close()
    return n, e, qs


def test_parallel_output_matches_serial_on_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reset_pool_hook()
    src = tmp_path / "src"
    shutil.copytree(FIXTURE, src)

    def run_workers(w: str) -> tuple[int, int, list[tuple[str, float]]]:
        monkeypatch.setenv("OMNIX_INGEST_WORKERS", w)
        dbp = tmp_path / f"db_{w}.sqlite"
        if dbp.is_file():
            dbp.unlink()
        evolution.begin_evolution_run()
        s = GraphStore(str(dbp))
        qlog: list[tuple[str, float]] = []

        def track(
            g: str,
            q: float,
            _t: set[str],
            _k: object,
            *,
            parse_mode: str = "generic",
        ) -> None:
            _ = _t, _k, parse_mode
            qlog.append((g, float(q)))

        monkeypatch.setattr("src.parser.evolution.observe_parse", track)
        _ = ind.ingest_unified_codebase(str(src), s, parse_mode="generic")
        s.close()
        n, e, _ = _snapshot_graph(dbp)
        return n, e, qlog

    a_n, a_e, a_q = run_workers("1")
    b_n, b_e, b_q = run_workers("4")
    assert a_n == b_n
    assert a_e == b_e
    assert len(a_q) == len(b_q)
    for (ga, qa), (gb, qb) in zip(a_q, b_q, strict=True):
        assert ga == gb
        assert abs(qa - qb) < 0.001


def test_worker_count_respects_env_var(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reset_pool_hook()
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    monkeypatch.setenv("OMNIX_INGEST_WORKERS", "2")
    dbp = tmp_path / "d.sqlite"
    s = GraphStore(str(dbp))
    _ = ind.ingest_unified_codebase(str(tmp_path), s, parse_mode="generic")
    s.close()
    assert ingmod._LAST_PROCESS_POOL_MAX_WORKERS == 2  # type: ignore[misc]


def test_one_file_parse_error_does_not_abort_run(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    _reset_pool_hook()
    code = tmp_path / "code"
    code.mkdir()
    for name in ("a.py", "b.py", "bad.py", "c.py", "d.py"):
        (code / name).write_text("y = 2\n", encoding="utf-8")
    monkeypatch.setenv("OMNIX_TEST_FORCE_PARSE_ERROR_BASENAME", "bad.py")
    monkeypatch.setenv("OMNIX_INGEST_WORKERS", "2")
    dbp = tmp_path / "o.sqlite"
    s = GraphStore(str(dbp))
    tot = ind.ingest_unified_codebase(str(code), s, parse_mode="generic")
    s.close()
    s2 = GraphStore(str(dbp))
    tot2 = s2.node_count()
    s2.close()
    assert tot2 > 0
    assert tot.skip.n_parsed_files == 4
    assert tot.errors >= 1
    with sqlite3.connect(dbp) as c:
        row = c.execute(
            "SELECT files FROM skip_summary WHERE reason=?", ("parse_error",)
        ).fetchone()
    assert row is not None
    assert int(row[0]) >= 1


def test_batch_commit_atomicity_on_simulated_crash(tmp_path: Path) -> None:
    dbp = tmp_path / "t.db"
    s = GraphStore(str(dbp))
    s.begin_batch()
    s.import_graph_snapshot(
        [
            {
                "id": "f",
                "name": "f",
                "type": "file",
                "file_path": "x",
                "start_line": 1,
                "end_line": 1,
                "complexity": 1,
                "metadata": None,
            }
        ],
        [],
    )
    with mock.patch.object(GraphStore, "commit_batch", side_effect=OSError("boom")):
        with pytest.raises(OSError):
            s.commit_batch()
    s.close()
    s3 = GraphStore(str(dbp))
    assert s3.node_count() == 0
    s3.close()
