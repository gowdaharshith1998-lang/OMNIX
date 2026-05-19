"""GraphStore threading.RLock serializes access."""

from __future__ import annotations

import tempfile
import threading
from concurrent.futures import ThreadPoolExecutor, wait
from pathlib import Path

import pytest

from omnix.graph.store import GraphStore


def test_locked_connection_select(tmp_path: Path) -> None:
    db = tmp_path / "l.sqlite"
    s = GraphStore(str(db))
    try:
        with s.locked_connection() as c:
            assert c.execute("SELECT 1").fetchone()[0] == 1
    finally:
        s.close()


def test_sqlite_connection_raw_still_returns_connection(tmp_path: Path) -> None:
    db = tmp_path / "r.sqlite"
    s = GraphStore(str(db))
    try:
        con = s.sqlite_connection()
        assert con.execute("SELECT 2").fetchone()[0] == 2
    finally:
        s.close()


def test_concurrent_writes_serialized(tmp_path: Path) -> None:
    db = tmp_path / "c.sqlite"
    s = GraphStore(str(db))

    def worker(i: int) -> None:
        s.add_node(f"id-{i}", f"n{i}", "function", file_path=f"f{i}.py")

    try:
        with ThreadPoolExecutor(max_workers=8) as ex:
            futs = [ex.submit(worker, i) for i in range(40)]
            wait(futs)
            for f in futs:
                f.result()
        assert s.node_count() == 40
    finally:
        s.close()


def test_rlock_nested_locked_connection(tmp_path: Path) -> None:
    db = tmp_path / "n.sqlite"
    s = GraphStore(str(db))
    try:
        with s.locked_connection():
            with s.locked_connection() as c:
                assert c.execute("SELECT 3").fetchone()[0] == 3
    finally:
        s.close()


def test_store_has_rlock() -> None:
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        path = f.name
    s = GraphStore(path)
    try:
        assert hasattr(s, "_lock")
        assert isinstance(s._lock, type(threading.RLock()))
    finally:
        s.close()
