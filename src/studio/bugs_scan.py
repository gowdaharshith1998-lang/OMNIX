"""Studio async wrapper for the existing PBT bug scanner."""

from __future__ import annotations

import asyncio
import os
import threading
import time
from typing import Any

from src.find_bugs.runner import run_find_bugs
from src.studio.parser_bridge import broadcast_to_workspace
from src.studio.workspace import Workspace
from src.studio.ws_protocol import (
    msg_bugs_scan_complete,
    msg_bugs_scan_error,
    msg_bugs_scan_heartbeat,
    msg_bugs_scan_started,
)

HEARTBEAT_SECONDS = 5.0
STUDIO_RSS_CAP_BYTES = 1024 * 1024 * 1024
_RSS_CAP_ENV_LOCK = threading.Lock()


def _schedule_broadcast(
    loop: asyncio.AbstractEventLoop, workspace: Workspace, message: dict[str, Any]
) -> None:
    try:
        loop.call_soon_threadsafe(
            asyncio.create_task, broadcast_to_workspace(workspace, message)
        )
    except RuntimeError:
        return


def _start_heartbeat_thread(
    *,
    loop: asyncio.AbstractEventLoop,
    workspace: Workspace,
    scan_id: str,
    started_at: float,
) -> threading.Event:
    stop_event = threading.Event()

    def heartbeat() -> None:
        while not stop_event.wait(HEARTBEAT_SECONDS):
            _schedule_broadcast(
                loop,
                workspace,
                msg_bugs_scan_heartbeat(scan_id, time.time() - started_at),
            )

    threading.Thread(target=heartbeat, daemon=True, name=f"bugs-scan-{scan_id}").start()
    return stop_event


async def run_scan_for_workspace(
    workspace: Workspace, scan_id: str
) -> dict[str, Any]:
    """Run find-bugs without blocking the Studio event loop."""
    started_at = time.time()
    await broadcast_to_workspace(
        workspace,
        msg_bugs_scan_started(scan_id, started_at, str(workspace.root)),
    )
    loop = asyncio.get_running_loop()
    stop_event = _start_heartbeat_thread(
        loop=loop,
        workspace=workspace,
        scan_id=scan_id,
        started_at=started_at,
    )
    try:
        await asyncio.to_thread(_RSS_CAP_ENV_LOCK.acquire)
        prior_cap = os.environ.get("OMNIX_FIND_BUGS_RSS_CAP_BYTES")
        os.environ["OMNIX_FIND_BUGS_RSS_CAP_BYTES"] = str(STUDIO_RSS_CAP_BYTES)
        try:
            exit_code, output_text, detail = await asyncio.to_thread(
                run_find_bugs,
                codebase_path=str(workspace.root),
                graph_db=str(workspace.store.db_path),
                json_mode=True,
            )
        finally:
            if prior_cap is None:
                os.environ.pop("OMNIX_FIND_BUGS_RSS_CAP_BYTES", None)
            else:
                os.environ["OMNIX_FIND_BUGS_RSS_CAP_BYTES"] = prior_cap
            _RSS_CAP_ENV_LOCK.release()
        if exit_code == 2 or detail is None:
            message = output_text.strip() or "find-bugs scan failed"
            await broadcast_to_workspace(
                workspace,
                msg_bugs_scan_error(scan_id, message, "runner_error"),
            )
            return {
                "scan_id": scan_id,
                "exit_code": exit_code,
                "ok": False,
                "error_message": message,
            }
        summary = detail.get("summary") if isinstance(detail.get("summary"), dict) else {}
        findings = detail.get("findings") if isinstance(detail.get("findings"), list) else []
        wall_time = float(summary.get("wall_time_seconds") or (time.time() - started_at))
        await broadcast_to_workspace(
            workspace,
            msg_bugs_scan_complete(scan_id, findings, summary, wall_time),
        )
        return {
            "scan_id": scan_id,
            "exit_code": exit_code,
            "ok": True,
            "findings_count": len(findings),
            "summary": summary,
        }
    except Exception as exc:  # noqa: BLE001
        await broadcast_to_workspace(
            workspace,
            msg_bugs_scan_error(scan_id, str(exc), exc.__class__.__name__),
        )
        return {
            "scan_id": scan_id,
            "exit_code": 2,
            "ok": False,
            "error_message": str(exc),
        }
    finally:
        stop_event.set()
