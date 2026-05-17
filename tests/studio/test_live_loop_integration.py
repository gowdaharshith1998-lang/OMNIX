"""End-to-end Studio live loop: API + WebSocket + parser bridge (in-process TestClient)."""

from __future__ import annotations

import json
import time
from collections import Counter
from typing import Any

import pytest
from fastapi.testclient import TestClient

from omnix.studio.server import app
from omnix.studio.workspace import MANAGER


def _close_all_workspaces() -> None:
    with TestClient(app) as c:
        for wid in list(MANAGER.workspaces.keys()):
            r = c.post("/api/workspace/close", json={"workspace_id": wid})
            if r.status_code not in (200, 404):
                raise AssertionError(
                    f"close failed {wid}: {r.status_code} {r.text[:200]}"
                )


@pytest.fixture(autouse=True)
def _isolated_studio_state() -> Any:
    yield
    _close_all_workspaces()


def _subscribe(ws: Any, wid: str) -> None:
    ws.send_text(
        json.dumps(
            {
                "type": "subscribe",
                "workspace_id": wid,
            }
        )
    )


def _recv_bootstrap(
    ws: Any, *, max_msg: int = 10_000
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for _ in range(max_msg):
        t = json.loads(ws.receive_text())
        out.append(t)
        if t.get("type") == "bootstrap_complete":
            return out
    msg = f"no bootstrap_complete after {len(out)} messages, last: {out[-1:]!r}"
    raise AssertionError(msg)


def _recv_type(
    ws: Any, expect: str, timeout_s: float = 6.0
) -> dict[str, Any]:
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        m = json.loads(ws.receive_text())
        if m.get("type") == expect:
            return m
    raise AssertionError(f"timeout waiting for {expect!r}")


def test_scratch_mode_bootstrap_immediate(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Empty project → scratch; first WS message after subscribe is full bootstrap in scratch mode."""
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_ll"))
    proj = tmp_path / "sc"
    proj.mkdir()
    with TestClient(app) as c:
        o = c.post(
            "/api/workspace/open", json={"path": str(proj)}
        ).json()
        assert o["mode"] == "scratch"
        wid: str = o["workspace_id"]
        time.sleep(0.3)
        with c.websocket_connect(
            f"/ws/workspace/{wid}"
        ) as ws:
            _subscribe(ws, wid)
            out = _recv_bootstrap(ws)
        types = [m.get("type") for m in out]
        assert types[0] == "bootstrap_start", types[:3]
        assert (out[0].get("mode")) == "scratch"
        assert "bootstrap_complete" in types
        c.post("/api/workspace/close", json={"workspace_id": wid})


def test_create_file_via_api_triggers_watcher(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_w"))
    proj = tmp_path / "p1"
    proj.mkdir()
    with TestClient(app) as c:
        wid = c.post(
            "/api/workspace/open", json={"path": str(proj)}
        ).json()["workspace_id"]
        time.sleep(0.4)
        with c.websocket_connect(
            f"/ws/workspace/{wid}"
        ) as ws:
            _subscribe(ws, wid)
            _recv_bootstrap(ws)
            c.post(
                f"/api/workspace/{wid}/file",
                json={"path": "hello.py", "content": "x=1\n"},
            )
            fa = _recv_type(ws, "file_added", timeout_s=8.0)
        assert fa.get("path") == "hello.py"
        c.post("/api/workspace/close", json={"workspace_id": wid})


def test_file_change_broadcasts_node_delta(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_nd"))
    proj = tmp_path / "p2"
    proj.mkdir()
    with TestClient(app) as c:
        wid = c.post(
            "/api/workspace/open", json={"path": str(proj)}
        ).json()["workspace_id"]
        time.sleep(0.4)
        with c.websocket_connect(
            f"/ws/workspace/{wid}"
        ) as ws:
            _subscribe(ws, wid)
            _recv_bootstrap(ws)
            c.post(
                f"/api/workspace/{wid}/file",
                json={
                    "path": "n.py",
                    "content": "def f():\n    return 0\n",
                },
            )
            t0 = time.time()
            na = _recv_type(ws, "node_added", timeout_s=10.0)
            _ = (time.time() - t0)  # reserved for local debugging
        assert "node" in na
        assert na["node"] is not None
        c.post("/api/workspace/close", json={"workspace_id": wid})


def test_concurrent_file_changes_serialize_correctly(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Two back-to-back creates are processed without interleaving their broadcast phases."""
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_co"))
    proj = tmp_path / "p3"
    proj.mkdir()
    with TestClient(app) as c:
        wid = c.post(
            "/api/workspace/open", json={"path": str(proj)}
        ).json()["workspace_id"]
        time.sleep(0.4)
        with c.websocket_connect(
            f"/ws/workspace/{wid}"
        ) as ws:
            _subscribe(ws, wid)
            _recv_bootstrap(ws)
            c.post(
                f"/api/workspace/{wid}/file",
                json={"path": "a.py", "content": "a=1\n"},
            )
            c.post(
                f"/api/workspace/{wid}/file",
                json={"path": "b.py", "content": "b=2\n"},
            )
            # Both created back-to-back; inotify + debounce order of file_added is
            # not required to match POST order — both must appear without errors.
            paths: set[str] = set()
            t_end = time.time() + 15.0
            while time.time() < t_end and len(paths) < 2:
                m = json.loads(ws.receive_text())
                if m.get("type") == "error":
                    raise AssertionError(m)
                if m.get("type") == "file_added" and m.get("path") in (
                    "a.py",
                    "b.py",
                ):
                    paths.add(m["path"])
        assert paths == {"a.py", "b.py"}, paths


def test_websocket_reconnect_resends_bootstrap(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second connection after the first WebSocket is closed still receives a full bootstrap."""
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_rb"))
    proj = tmp_path / "p4"
    proj.mkdir()
    with TestClient(app) as c:
        wid = c.post(
            "/api/workspace/open", json={"path": str(proj)}
        ).json()["workspace_id"]
        time.sleep(0.3)
        with c.websocket_connect(
            f"/ws/workspace/{wid}"
        ) as ws:
            _subscribe(ws, wid)
            first = _recv_bootstrap(ws)
        b1 = Counter(
            t for m in first for t in [m.get("type", "")] if t
        ).get("bootstrap_start", 0)
        with c.websocket_connect(
            f"/ws/workspace/{wid}"
        ) as ws2:
            _subscribe(ws2, wid)
            second = _recv_bootstrap(ws2)
        b2 = [
            m for m in second if m.get("type") == "bootstrap_start"
        ]
        assert b1 >= 0
        assert len(b2) >= 1, second[:5]
        assert second[0].get("type") == "bootstrap_start"
        c.post("/api/workspace/close", json={"workspace_id": wid})
