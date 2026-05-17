"""Ephemeral per-workspace state under ``~/.omnix/sessions/<id>``."""

from __future__ import annotations

import asyncio
import json
import shutil
from pathlib import Path

from omnix.studio.paths import ensure_global_omnix_dir


def _session_path(workspace_id: str) -> Path:
    return (ensure_global_omnix_dir() / "sessions" / workspace_id).resolve()


def ensure_session_artifact(workspace_id: str) -> None:
    p = _session_path(workspace_id)
    p.mkdir(parents=True, exist_ok=True)
    meta = p / "meta.json"
    if not meta.is_file():
        meta.write_text(
            json.dumps({"workspace_id": workspace_id, "v": 1}, indent=2) + "\n", encoding="utf-8"  # noqa: E501
        )


async def remove_session_dir(workspace_id: str) -> None:
    p = _session_path(workspace_id)
    if p.is_dir():

        def _rm() -> None:
            shutil.rmtree(p, ignore_errors=True)

        await asyncio.get_event_loop().run_in_executor(None, _rm)
