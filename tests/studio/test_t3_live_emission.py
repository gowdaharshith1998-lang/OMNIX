"""T3 — debt-13: ParserBridge → WebSocket broadcast chain (integration)."""

from __future__ import annotations

import json
import time
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


def _recv_bootstrap(ws: Any, *, max_msg: int = 10_000) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for _ in range(max_msg):
        t = json.loads(ws.receive_text())
        out.append(t)
        if t.get("type") == "bootstrap_complete":
            return out
    raise AssertionError(f"no bootstrap_complete after {len(out)} messages")


def _recv_until_types(
    ws: Any,
    want: set[str],
    *,
    timeout_s: float = 15.0,
) -> list[dict[str, Any]]:
    """Drain WS until one message has type in *want* or timeout."""
    t0 = time.time()
    got: list[dict[str, Any]] = []
    while time.time() - t0 < timeout_s:
        m = json.loads(ws.receive_text())
        got.append(m)
        if m.get("type") in want:
            return got
        if m.get("type") == "error":
            raise AssertionError(m)
    raise AssertionError(f"timeout waiting for any of {want!r}, got types={[x.get('type') for x in got[-8:]]}")


def test_edit_existing_file_emits_node_modified_via_bridge(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """Modify tracked file; ParserBridge must emit node_modified (or add/remove pair)."""
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_t3"))
    caplog.set_level("INFO", logger="omnix.studio.parser_bridge")

    proj = tmp_path / "proj"
    proj.mkdir()
    py = proj / "edited.py"
    py.write_text(
        "def foo():\n    return 1\n",
        encoding="utf-8",
        newline="\n",
    )

    with TestClient(app) as c:
        wid = c.post("/api/workspace/open", json={"path": str(proj)}).json()[
            "workspace_id"
        ]
        time.sleep(0.8)
        w = MANAGER.get(wid)
        assert w is not None
        br = w.parse_bridge
        assert br is not None

        with c.websocket_connect(f"/ws/workspace/{wid}") as ws:
            _subscribe(ws, wid)
            _recv_bootstrap(ws)

            py.write_text(
                "def foo():\n    return 42\n",
                encoding="utf-8",
                newline="\n",
            )
            br.on_filesystem("edited.py", "modified")
            got = _recv_until_types(
                ws,
                {"node_modified", "node_added", "node_removed"},
                timeout_s=15.0,
            )
            last = got[-1]
            assert last.get("type") in (
                "node_modified",
                "node_added",
                "node_removed",
            ), last

        c.post("/api/workspace/close", json={"workspace_id": wid})


def test_add_new_function_emits_node_added(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_t3b"))
    proj = tmp_path / "proj2"
    proj.mkdir()
    base = proj / "grow.py"
    base.write_text("def a():\n    pass\n", encoding="utf-8")

    with TestClient(app) as c:
        wid = c.post("/api/workspace/open", json={"path": str(proj)}).json()[
            "workspace_id"
        ]
        time.sleep(0.8)
        w = MANAGER.get(wid)
        assert w is not None
        br = w.parse_bridge
        assert br is not None

        with c.websocket_connect(f"/ws/workspace/{wid}") as ws:
            _subscribe(ws, wid)
            _recv_bootstrap(ws)

            base.write_text(
                "def a():\n    pass\n\ndef b():\n    pass\n",
                encoding="utf-8",
                newline="\n",
            )
            br.on_filesystem("grow.py", "modified")
            got = _recv_until_types(ws, {"node_added"}, timeout_s=15.0)
            assert got[-1].get("type") == "node_added"
            assert got[-1].get("node")

        c.post("/api/workspace/close", json={"workspace_id": wid})


def test_delete_file_emits_node_removed(
    tmp_path: Any, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_t3c"))
    proj = tmp_path / "proj3"
    proj.mkdir()
    victim = proj / "gone.py"
    victim.write_text("def x():\n    return 0\n", encoding="utf-8")

    with TestClient(app) as c:
        wid = c.post("/api/workspace/open", json={"path": str(proj)}).json()[
            "workspace_id"
        ]
        time.sleep(0.8)
        w = MANAGER.get(wid)
        assert w is not None
        br = w.parse_bridge
        assert br is not None

        with c.websocket_connect(f"/ws/workspace/{wid}") as ws:
            _subscribe(ws, wid)
            _recv_bootstrap(ws)

            victim.unlink()
            br.on_filesystem("gone.py", "deleted")
            got = _recv_until_types(ws, {"node_removed"}, timeout_s=15.0)
            assert got[-1].get("type") == "node_removed"
            assert got[-1].get("node_id")

        c.post("/api/workspace/close", json={"workspace_id": wid})
