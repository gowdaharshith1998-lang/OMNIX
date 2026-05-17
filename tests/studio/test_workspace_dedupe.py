"""Workspace open dedupes by canonical project root."""

from __future__ import annotations

import asyncio
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from omnix.studio.server import app
from omnix.studio.workspace import MANAGER, open_workspace


def test_find_by_root_matches_realpath(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_fd"))
    p = tmp_path / "proj"
    p.mkdir()
    w, _ = open_workspace(str(p))
    MANAGER.put(w)
    try:
        q = MANAGER.find_by_root(Path(os.path.realpath(str(p))))
        assert q is not None and q.id == w.id
        assert MANAGER.find_by_root(Path("/nonexistent_abs_path_omnix_xyz")) is None
    finally:
        asyncio.run(w.stop())
        MANAGER.remove(w.id)


def test_api_open_reuses_workspace_id(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_fd2"))
    proj = tmp_path / "same"
    proj.mkdir()
    with TestClient(app) as c:
        a = c.post("/api/workspace/open", json={"path": str(proj)}).json()
        b = c.post("/api/workspace/open", json={"path": str(proj)}).json()
        assert a["workspace_id"] == b["workspace_id"]
        c.post("/api/workspace/close", json={"workspace_id": a["workspace_id"]})


def test_api_open_symlink_same_canonical(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_fd3"))
    real = tmp_path / "real_proj"
    real.mkdir()
    link = tmp_path / "link_proj"
    try:
        link.symlink_to(real, target_is_directory=True)
    except OSError:
        pytest.skip("symlink not supported")
    with TestClient(app) as c:
        a = c.post("/api/workspace/open", json={"path": str(real)}).json()
        b = c.post("/api/workspace/open", json={"path": str(link)}).json()
        assert a["workspace_id"] == b["workspace_id"]
        c.post("/api/workspace/close", json={"workspace_id": a["workspace_id"]})


def test_broken_workspace_removed_and_recreated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_fd4"))
    proj = tmp_path / "brk"
    proj.mkdir()
    with TestClient(app) as c:
        first = c.post("/api/workspace/open", json={"path": str(proj)}).json()
        wid1 = first["workspace_id"]
        w = MANAGER.get(wid1)
        assert w is not None
        w.store.close()
        second = c.post("/api/workspace/open", json={"path": str(proj)}).json()
        wid2 = second["workspace_id"]
        assert wid2 != wid1
        c.post("/api/workspace/close", json={"workspace_id": wid2})


def test_is_workspace_broken_ingest_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from src.studio.workspace import _is_workspace_broken

    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_fd5"))
    p = tmp_path / "x"
    p.mkdir()
    w, _ = open_workspace(str(p))
    assert not _is_workspace_broken(w)
    w.ingest_error = "boom"
    assert _is_workspace_broken(w)
    w.store.close()
