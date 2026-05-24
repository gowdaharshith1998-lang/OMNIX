from __future__ import annotations

import subprocess
from collections.abc import Callable
from pathlib import Path

import pytest

from omnix.graph.store import GraphStore


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=str(repo),
        capture_output=True,
        text=True,
        check=True,
    )
    return proc.stdout.strip()


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    (repo / "src").mkdir(parents=True)
    (repo / "tests").mkdir()
    (repo / "src" / "app.py").write_text(
        "def target():\n    return callee()\n\n"
        "def callee():\n    return 1\n",
        encoding="utf-8",
    )
    (repo / "src" / "caller.py").write_text(
        "from src.app import target\n\n"
        "def caller():\n    return target()\n\n"
        "def caller2():\n    return caller()\n",
        encoding="utf-8",
    )
    (repo / "tests" / "test_app.py").write_text(
        "from src.app import target\n\n"
        "def test_target():\n    assert target() == 1\n",
        encoding="utf-8",
    )
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.com")
    _git(repo, "config", "user.name", "Test User")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


@pytest.fixture
def git_head() -> Callable[[Path], str]:
    return lambda repo: _git(repo, "rev-parse", "HEAD")


@pytest.fixture
def git_cmd() -> Callable[[Path, str], str]:
    def run(repo: Path, *args: str) -> str:
        return _git(repo, *args)

    return run


@pytest.fixture
def make_graph_db() -> Callable[[Path, str | None], Path]:
    def make(repo: Path, indexed_commit: str | None = None) -> Path:
        omnix_dir = repo / ".omnix"
        omnix_dir.mkdir(exist_ok=True)
        db_path = omnix_dir / "omnix.db"
        store = GraphStore(str(db_path))
        store.add_node("src/app.py::target", "target", "function", "src/app.py", 1, 2)
        store.add_node("src/app.py::callee", "callee", "function", "src/app.py", 4, 5)
        store.add_node("src/caller.py::caller", "caller", "function", "src/caller.py", 3, 4)
        store.add_node("src/caller.py::caller2", "caller2", "function", "src/caller.py", 6, 7)
        store.add_node("tests/test_app.py::test_target", "test_target", "function", "tests/test_app.py", 3, 4)
        store.add_edge("src/caller.py::caller", "src/app.py::target", "CALLS")
        store.add_edge("src/caller.py::caller2", "src/caller.py::caller", "CALLS")
        store.add_edge("src/app.py::target", "src/app.py::callee", "CALLS")
        store.add_edge("tests/test_app.py::test_target", "src/app.py::target", "CALLS")
        store.set_file_hash("src/app.py", "a" * 64, 1.0, node_count=2, edge_count=1)
        store.set_file_hash("src/caller.py", "b" * 64, 1.0, node_count=2, edge_count=2)
        store.set_file_hash("tests/test_app.py", "c" * 64, 1.0, node_count=1, edge_count=1)
        if indexed_commit is not None:
            store.set_meta("indexed_commit", indexed_commit)
        store.set_meta("indexed_at", "2026-05-24T02:30:15Z")
        store.commit()
        store.close()
        return db_path

    return make
