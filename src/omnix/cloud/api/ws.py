"""WebSocket — streams JobEvents to the connected operator.

Delta format reuses the M4.2 Studio CHAT shape so the existing renderer
just works.
"""

from __future__ import annotations

import asyncio

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from omnix.cloud import events

router = APIRouter()


@router.websocket("/ws/jobs/{job_id}")
async def ws_job(ws: WebSocket, job_id: str):
    await ws.accept()
    queue_task: asyncio.Task | None = None
    try:
        async for ev in events.subscribe(job_id, replay=True):
            await ws.send_json(
                {
                    "type": "gate_event",
                    "job_id": ev.job_id,
                    "seq": ev.seq,
                    "gate": ev.gate,
                    "severity": ev.severity,
                    "message": ev.message,
                    "payload": ev.payload,
                    "ts": ev.ts,
                }
            )
    except WebSocketDisconnect:
        return
    finally:
        if queue_task and not queue_task.done():
            queue_task.cancel()
