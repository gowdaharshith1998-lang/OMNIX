"""API round-trip for drill-down save: PUT file, conflicts, and watcher + delta."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from src.studio.server import app


def _sub(ws: Any, wid: str) -> None:
    ws.send_text(
        json.dumps(
            {
                "type": "subscribe",
                "workspace_id": wid,
            }
        )
    )


def _recv_bootstrap(ws: Any, *, max_msg: int = 10_000) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for _ in range(max_msg):
        t = json.loads(ws.receive_text())
        out.append(t)
        if t.get("type") == "bootstrap_complete":
            return out
    msg = f"no bootstrap_complete after {len(out)}"
    raise AssertionError(msg)


def _recv_type(
    ws: Any,
    *expect: str,
    timeout_s: float = 6.0,
) -> dict[str, Any]:
    want = set(expect)
    t0 = time.time()
    while time.time() - t0 < timeout_s:
        m = json.loads(ws.receive_text())
        t = m.get("type")
        if t in want:
            return m
    raise AssertionError(f"timeout; wanted one of {want!r}")


def test_put_file_writes_to_disk(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_dd1"))
    proj = tmp_path / "proj1"
    proj.mkdir()
    with TestClient(app) as c:
        w = c.post(
            "/api/workspace/open", json={"path": str(proj)}
        ).json()
        wid: str = w["workspace_id"]
        c.post(
            f"/api/workspace/{wid}/file",
            json={"path": "foo.py", "content": "a = 0\n"},
        )
        f = Path(proj) / "foo.py"
        assert f.is_file()
        r0 = c.get(
            f"/api/workspace/{wid}/file", params={"path": "foo.py"}
        )
        m0 = float(r0.json()["last_modified"])
        body = {
            "path": "foo.py",
            "content": "x = 42\n",
            "expected_last_modified": m0,
        }
        u = c.put(
            f"/api/workspace/{wid}/file", json=body
        )
        assert u.status_code == 200, u.text
        uj = u.json()
        assert uj.get("written") is True
        assert "new_last_modified" in uj
        assert f.read_text(encoding="utf-8", errors="strict") == "x = 42\n"
        time.sleep(0.5)
        c.post(
            "/api/workspace/close", json={"workspace_id": wid}
        )


def test_put_file_conflict_returns_409(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_dd2"))
    proj = tmp_path / "proj2"
    proj.mkdir()
    with TestClient(app) as c:
        wid = c.post(
            "/api/workspace/open", json={"path": str(proj)}
        ).json()["workspace_id"]
        c.post(
            f"/api/workspace/{wid}/file",
            json={"path": "z.py", "content": "v=1\n"},
        )
        r0 = c.get(
            f"/api/workspace/{wid}/file", params={"path": "z.py"}
        )
        m0 = float(r0.json()["last_modified"])
        bad = c.put(
            f"/api/workspace/{wid}/file",
            json={
                "path": "z.py",
                "content": "v=2\n",
                "expected_last_modified": m0 - 9000.0,
            },
        )
        assert bad.status_code == 409, bad.text
        time.sleep(0.5)
        c.post(
            "/api/workspace/close", json={"workspace_id": wid}
        )


def test_put_file_triggers_watcher_and_delta(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """PUT after API-created file: watcher re-parse → graph delta (see live loop tests)."""
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_dd3"))
    proj = tmp_path / "proj3"
    proj.mkdir()
    with TestClient(app) as c:
        w = c.post(
            "/api/workspace/open", json={"path": str(proj)}
        ).json()
        wid: str = w["workspace_id"]
        time.sleep(0.4)
        with c.websocket_connect(
            f"/ws/workspace/{wid}"
        ) as ws:
            _sub(ws, wid)
            _recv_bootstrap(ws)
            c.post(
                f"/api/workspace/{wid}/file",
                json={"path": "bar.py", "content": "def a():\n    return 1\n"},
            )
            _ = _recv_type(ws, "node_added", "file_added", timeout_s=10.0)
            r0 = c.get(
                f"/api/workspace/{wid}/file", params={"path": "bar.py"}
            )
            m0 = float(r0.json()["last_modified"])
            t0 = time.time()
            u = c.put(
                f"/api/workspace/{wid}/file",
                json={
                    "path": "bar.py",
                    "content": "def a():\n    return 99\n",
                    "expected_last_modified": m0,
                },
            )
            assert u.status_code == 200, u.text
            m = _recv_type(ws, "node_added", "node_modified", timeout_s=8.0)
            assert time.time() - t0 < 2.0, "graph delta should follow PUT quickly"
            assert m.get("type") in ("node_added", "node_modified")
            time.sleep(0.3)
        time.sleep(0.5)
        c.post(
            "/api/workspace/close", json={"workspace_id": wid}
        )
