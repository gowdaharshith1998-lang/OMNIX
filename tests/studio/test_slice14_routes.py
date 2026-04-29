"""Slice 14 route coverage for file tree, receipts, and graph search."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.studio.server import app
from src.studio.workspace import MANAGER, open_workspace


def _open_managed_workspace(
    root: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> str:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "global"))
    w, _stats = open_workspace(str(root))
    MANAGER.put(w)
    return w.id


def _cleanup_workspace(workspace_id: str) -> None:
    w = MANAGER.get(workspace_id)
    if w is not None:
        asyncio.run(w.stop())
    MANAGER.remove(workspace_id)


def test_files_tree_empty_repo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    project = tmp_path / "empty"
    project.mkdir()
    workspace_id = _open_managed_workspace(project, tmp_path, monkeypatch)
    try:
        client = TestClient(app)
        res = client.get(f"/api/workspace/{workspace_id}/files/tree")
        assert res.status_code == 200
        assert res.json()["tree"]["children"] == []
    finally:
      _cleanup_workspace(workspace_id)


def test_files_tree_populated_repo_skips_noise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "proj"
    (project / "src").mkdir(parents=True)
    (project / "src" / "app.py").write_text("x=1\n", encoding="utf-8")
    (project / ".git").mkdir()
    (project / ".git" / "HEAD").write_text("ref: main\n", encoding="utf-8")
    (project / "node_modules").mkdir()
    (project / "node_modules" / "pkg.js").write_text("", encoding="utf-8")
    workspace_id = _open_managed_workspace(project, tmp_path, monkeypatch)
    try:
        client = TestClient(app)
        res = client.get(f"/api/workspace/{workspace_id}/files/tree")
        assert res.status_code == 200
        body = json.dumps(res.json())
        assert "app.py" in body
        assert "node_modules" not in body
        assert ".git" not in body
    finally:
        _cleanup_workspace(workspace_id)


def test_receipts_route_reads_existing_receipts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    receipt_dir = tmp_path / "home" / ".omnix" / "receipts"
    receipt_dir.mkdir(parents=True)
    (receipt_dir / "call_20260429Z_abc.json").write_text(
        json.dumps({"call_id": "abc", "provider": "openai"}),
        encoding="utf-8",
    )
    (receipt_dir / "call_20260429Z_abc.sig").write_text("sig", encoding="ascii")
    monkeypatch.setattr(Path, "home", lambda: tmp_path / "home")
    workspace_id = _open_managed_workspace(project, tmp_path, monkeypatch)
    try:
        client = TestClient(app)
        res = client.get(f"/api/workspace/{workspace_id}/receipts")
        assert res.status_code == 200
        rows = res.json()["receipts"]
        assert rows[0]["source"] == "fabric"
        assert rows[0]["sig_alg"] == "ML-DSA-65"
    finally:
        _cleanup_workspace(workspace_id)


def test_search_route_returns_graph_symbols(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    workspace_id = _open_managed_workspace(project, tmp_path, monkeypatch)
    w = MANAGER.get(workspace_id)
    assert w is not None
    c = w.store.sqlite_connection()
    c.execute(
        "INSERT INTO nodes (id, name, type, file_path, start_line, end_line, complexity, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("n1", "run_handler", "function", "src/app.py", 12, 16, 1, "{}"),
    )
    w.store.commit()
    try:
        client = TestClient(app)
        res = client.get(f"/api/workspace/{workspace_id}/search?q=run&kind=symbol")
        assert res.status_code == 200
        assert res.json()["results"][0] == {
            "kind": "symbol",
            "name": "run_handler",
            "path": "src/app.py",
            "line": 12,
            "snippet": "",
        }
    finally:
        _cleanup_workspace(workspace_id)
