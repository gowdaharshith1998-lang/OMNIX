"""Studio bugs scan route and WebSocket lifecycle coverage."""

from __future__ import annotations

import asyncio
import os
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from omnix.studio.server import app
from omnix.studio.workspace import MANAGER, open_workspace


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


def _wait_for(predicate: Any, timeout_s: float = 2.0) -> None:
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        if predicate():
            return
        time.sleep(0.02)
    raise AssertionError("condition was not met before timeout")


def test_bugs_scan_route_starts_background_scan_and_uses_studio_db(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    (project / "app.py").write_text("def unsafe_div(x):\n    return 1 / x\n", encoding="utf-8")
    workspace_id = _open_managed_workspace(project, tmp_path, monkeypatch)
    w = MANAGER.get(workspace_id)
    assert w is not None
    calls: list[dict[str, Any]] = []
    messages: list[dict[str, Any]] = []

    def fake_run_find_bugs(**kwargs: Any) -> tuple[int, str, dict[str, Any]]:
        calls.append(kwargs)
        return (
            1,
            "{}\n",
            {
                "summary": {"findings_count": 1, "wall_time_seconds": 0.01},
                "findings": [
                    {
                        "file": "app.py",
                        "function": "unsafe_div",
                        "lineno": 1,
                        "severity_score": 12,
                        "failures": [],
                    }
                ],
            },
        )

    async def fake_broadcast(_workspace: Any, message: dict[str, Any]) -> None:
        messages.append(message)

    monkeypatch.setattr("omnix.studio.bugs_scan.run_find_bugs", fake_run_find_bugs)
    monkeypatch.setattr("omnix.studio.bugs_scan.broadcast_to_workspace", fake_broadcast)
    try:
        with TestClient(app) as client:
            res = client.post(f"/api/workspace/{workspace_id}/bugs/scan")
            assert res.status_code == 202
            scan_id = res.json()["scan_id"]
            _wait_for(lambda: any(m.get("type") == "bugs_scan_complete" for m in messages))
            assert calls[0]["codebase_path"] == str(project.resolve())
            assert calls[0]["graph_db"] == str(w.store.db_path)
            assert calls[0]["json_mode"] is True
            assert messages[0]["type"] == "bugs_scan_started"
            assert messages[0]["scan_id"] == scan_id
            assert messages[-1]["type"] == "bugs_scan_complete"
            assert messages[-1]["findings"][0]["function"] == "unsafe_div"
            _wait_for(lambda: workspace_id not in MANAGER.active_bug_scans)
    finally:
        _cleanup_workspace(workspace_id)


def test_bugs_scan_route_broadcasts_runner_errors(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    workspace_id = _open_managed_workspace(project, tmp_path, monkeypatch)
    messages: list[dict[str, Any]] = []

    def fake_run_find_bugs(**_kwargs: Any) -> tuple[int, str, None]:
        return (2, "graph database path not usable\n", None)

    async def fake_broadcast(_workspace: Any, message: dict[str, Any]) -> None:
        messages.append(message)

    monkeypatch.setattr("omnix.studio.bugs_scan.run_find_bugs", fake_run_find_bugs)
    monkeypatch.setattr("omnix.studio.bugs_scan.broadcast_to_workspace", fake_broadcast)
    try:
        with TestClient(app) as client:
            res = client.post(f"/api/workspace/{workspace_id}/bugs/scan")
            assert res.status_code == 202
            _wait_for(lambda: any(m.get("type") == "bugs_scan_error" for m in messages))
            err = [m for m in messages if m.get("type") == "bugs_scan_error"][-1]
            assert err["error_kind"] == "runner_error"
            assert "graph database" in err["error_message"]
            _wait_for(lambda: workspace_id not in MANAGER.active_bug_scans)
    finally:
        _cleanup_workspace(workspace_id)


def test_bugs_scan_uses_1gb_rss_cap(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Studio raises RLIMIT_AS to 1GB for crypto/ML PBT scans; CLI default stays 512MB."""
    project = tmp_path / "proj"
    project.mkdir()
    workspace_id = _open_managed_workspace(project, tmp_path, monkeypatch)
    seen_caps: list[str | None] = []
    messages: list[dict[str, Any]] = []
    cap_env = "OMNIX_FIND_BUGS_RSS_CAP_BYTES"
    monkeypatch.delenv(cap_env, raising=False)

    def fake_run_find_bugs(**_kwargs: Any) -> tuple[int, str, dict[str, Any]]:
        seen_caps.append(os.environ.get(cap_env))
        return (0, "{}\n", {"summary": {"wall_time_seconds": 0.01}, "findings": []})

    async def fake_broadcast(_workspace: Any, message: dict[str, Any]) -> None:
        messages.append(message)

    monkeypatch.setattr("omnix.studio.bugs_scan.run_find_bugs", fake_run_find_bugs)
    monkeypatch.setattr("omnix.studio.bugs_scan.broadcast_to_workspace", fake_broadcast)
    try:
        with TestClient(app) as client:
            res = client.post(f"/api/workspace/{workspace_id}/bugs/scan")
            assert res.status_code == 202
            _wait_for(lambda: any(m.get("type") == "bugs_scan_complete" for m in messages))
            _wait_for(lambda: workspace_id not in MANAGER.active_bug_scans)
            assert seen_caps == [str(1024 * 1024 * 1024)]
            assert cap_env not in os.environ
    finally:
        _cleanup_workspace(workspace_id)


def test_bugs_scan_route_rejects_concurrent_scan(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    project = tmp_path / "proj"
    project.mkdir()
    workspace_id = _open_managed_workspace(project, tmp_path, monkeypatch)
    release = __import__("threading").Event()

    def fake_run_find_bugs(**_kwargs: Any) -> tuple[int, str, dict[str, Any]]:
        assert release.wait(2.0)
        return (0, "{}\n", {"summary": {"wall_time_seconds": 0.01}, "findings": []})

    async def fake_broadcast(_workspace: Any, _message: dict[str, Any]) -> None:
        return None

    monkeypatch.setattr("omnix.studio.bugs_scan.run_find_bugs", fake_run_find_bugs)
    monkeypatch.setattr("omnix.studio.bugs_scan.broadcast_to_workspace", fake_broadcast)
    try:
        with TestClient(app) as client:
            first = client.post(f"/api/workspace/{workspace_id}/bugs/scan")
            assert first.status_code == 202
            _wait_for(lambda: workspace_id in MANAGER.active_bug_scans)
            second = client.post(f"/api/workspace/{workspace_id}/bugs/scan")
            assert second.status_code == 409
            assert second.json() == {
                "detail": "Scan already in progress",
                "active_scan_id": first.json()["scan_id"],
            }
            release.set()
            _wait_for(lambda: workspace_id not in MANAGER.active_bug_scans)
    finally:
        release.set()
        _cleanup_workspace(workspace_id)
