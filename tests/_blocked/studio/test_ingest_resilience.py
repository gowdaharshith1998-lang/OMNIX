"""Initial ingest failure still signals ingest_event and WS clients."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from omnix.studio.server import app


def _recv_bootstrap_allow_ingest_err(ws, *, max_msg: int = 20_000) -> list[dict]:
    out: list[dict] = []
    for _ in range(max_msg):
        t = json.loads(ws.receive_text())
        out.append(t)
        if t.get("type") == "bootstrap_complete":
            return out
    raise AssertionError(f"no bootstrap_complete: last={out[-3:]!r}")


def test_ingest_failure_writes_audit_and_sets_event(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_ir"))

    def boom(workspace):  # noqa: ANN001
        raise RuntimeError("forced initial ingest failure for test")

    monkeypatch.setattr("omnix.studio.server._ingest_block", boom)
    proj = tmp_path / "proj"
    proj.mkdir()
    audit = tmp_path / ".omnix" / "audit" / "ingest_failures.log"
    with TestClient(app) as c:
        o = c.post("/api/workspace/open", json={"path": str(proj)}).json()
        wid = o["workspace_id"]
        import time

        time.sleep(0.2)
        with c.websocket_connect(f"/ws/workspace/{wid}") as ws:
            ws.send_json({"type": "subscribe", "workspace_id": wid})
            saw_err = False
            for _ in range(500):
                m = json.loads(ws.receive_text())
                if m.get("type") == "ingest_error":
                    saw_err = True
                    assert "forced initial ingest failure" in str(m.get("error", ""))
                    break
                if m.get("type") == "bootstrap_complete":
                    raise AssertionError("bootstrap completed without ingest_error")
            assert saw_err
            rest = _recv_bootstrap_allow_ingest_err(ws)
            types = [x.get("type") for x in rest]
            assert "bootstrap_start" in types
        c.post("/api/workspace/close", json={"workspace_id": wid})

    assert audit.is_file()
    line = audit.read_text(encoding="utf-8").strip().splitlines()[-1]
    rec = json.loads(line)
    assert rec["error_class"] == "RuntimeError"
    assert "forced initial ingest failure" in rec["error_message"]


def test_successful_ingest_no_ingest_error_ws_prefix(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("OMNIX_STUDIO_OMNIX_DIR", str(tmp_path / "g_ir2"))
    proj = tmp_path / "ok"
    proj.mkdir()
    with TestClient(app) as c:
        o = c.post("/api/workspace/open", json={"path": str(proj)}).json()
        wid = o["workspace_id"]
        import time

        time.sleep(0.6)
        with c.websocket_connect(f"/ws/workspace/{wid}") as ws:
            ws.send_json({"type": "subscribe", "workspace_id": wid})
            msgs = _recv_bootstrap_allow_ingest_err(ws)
        assert all(m.get("type") != "ingest_error" for m in msgs)
        c.post("/api/workspace/close", json={"workspace_id": wid})
