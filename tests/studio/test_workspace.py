"""Open/close workspace (isolated global OMNIX dir)."""

from __future__ import annotations

from pathlib import Path

import pytest

from omnix.studio import recent
from omnix.studio.paths import project_omnix_dir
from omnix.studio.workspace import open_workspace


def test_open_existing_folder_returns_existing_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g"))
    d = tmp_path / "ex"
    d.mkdir()
    (d / "f.py").write_text("x=1\n", encoding="utf-8")
    w, _s = open_workspace(str(d))
    assert w.mode == "existing"


def test_open_empty_folder_returns_scratch_mode(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g2"))
    e = tmp_path / "sc"
    e.mkdir()
    w, _s = open_workspace(str(e))
    assert w.mode == "scratch"


def test_open_creates_dot_omnix_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g3"))
    p = tmp_path / "o"
    p.mkdir()
    w, _s = open_workspace(str(p))
    d = project_omnix_dir(p)
    assert d.is_dir()
    assert (d / "omnix.db").is_file()
    assert w.store.db_path == str(d / "omnix.db")


def test_open_updates_recent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    d = tmp_path / "g4"
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(d))
    pr = tmp_path / "rec"
    pr.mkdir()
    recent.add_recent(str(pr))
    r = recent.list_recent()
    assert any(x["path"] == str(pr.resolve()) for x in r)


def test_close_stops_watcher(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import asyncio
    from unittest.mock import Mock

    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g5"))
    p = tmp_path / "c"
    p.mkdir()
    ws, _s = open_workspace(str(p))
    w = Mock()
    ws.set_watcher(w)
    asyncio.run(ws.stop())
    w.stop.assert_called_once()