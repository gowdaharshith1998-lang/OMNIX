"""Streaming ingest: walk order and batch commits."""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest

from omnix.find_bugs.walker import iter_dispatch_paths
from omnix.graph.store import GraphStore
from omnix.parser import ingest_dispatch as ind
from omnix.parser.skip_tracking import SkipAggregate


def test_streaming_preserves_walk_order(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "proj"
    root.mkdir()
    for i in range(20):
        (root / f"m{i:02d}.py").write_text(f"x_{i} = {i}\n", encoding="utf-8")

    paths = list(iter_dispatch_paths(root, skip_tracker=SkipAggregate()))
    expected_rels = [p.relative_to(root).as_posix() for p in paths]

    orig_parse = ind.ingest_one_path_parse_only

    def delayed_parse(job: tuple) -> dict:
        idx = int(job[0])
        time.sleep((19 - idx) * 0.015)
        return orig_parse(job)

    monkeypatch.setattr(ind, "ingest_one_path_parse_only", delayed_parse)
    monkeypatch.setattr(ind, "ProcessPoolExecutor", ThreadPoolExecutor)
    monkeypatch.setenv("OMNIX_INGEST_WORKERS", "8")

    import_order: list[str] = []
    real_import = GraphStore.import_graph_snapshot

    def tracking(self: GraphStore, nodes: list, edges: list) -> None:
        for n in nodes:
            if n.get("type") == "file" and n.get("file_path"):
                import_order.append(str(n["file_path"]))
                break
        return real_import(self, nodes, edges)

    monkeypatch.setattr(GraphStore, "import_graph_snapshot", tracking)

    db = tmp_path / "g.db"
    store = GraphStore(str(db))
    store.reset()
    tot = ind.IngestTotals()
    ind._run_ingest_parallel(store, root.resolve(), paths, "generic", tot)
    store.close()

    assert len(import_order) == len(expected_rels)
    assert import_order == expected_rels


def test_streaming_batch_flush_on_exhaustion(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "b"
    root.mkdir()
    for i in range(25):
        (root / f"f{i}.py").write_text("a = 1\n", encoding="utf-8")

    paths = list(iter_dispatch_paths(root, skip_tracker=SkipAggregate()))
    commits: list[int] = []
    orig_cb = GraphStore.commit_batch

    def count_commit(self: GraphStore) -> None:
        commits.append(1)
        return orig_cb(self)

    monkeypatch.setattr(GraphStore, "commit_batch", count_commit)
    monkeypatch.setattr(ind, "_BATCH_SIZE", 10)
    monkeypatch.setenv("OMNIX_INGEST_WORKERS", "1")

    db = tmp_path / "b.db"
    store = GraphStore(str(db))
    store.reset()
    tot = ind.IngestTotals()
    ind._run_ingest_parallel(store, root.resolve(), paths, "generic", tot)
    store.close()
    assert sum(commits) == 3
