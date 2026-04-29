"""Per-workspace state: graph store, watcher, WebSockets, ingest gate."""

from __future__ import annotations

import asyncio
import contextlib
import os
import sqlite3
import threading
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable

from src.graph.store import GraphStore, NodeRow
from src.studio.paths import ensure_project_omnix_dir, project_graph_db_path
from src.studio.session import ensure_session_artifact, remove_session_dir

if TYPE_CHECKING:
    from src.studio.parser_bridge import ParserBridge
    from src.studio.watcher import ProjectWatcher
    from starlette.websockets import WebSocket


def _is_empty_dir(p: Path) -> bool:
    """True when the project has no user-visible entries (``.omnix`` is ignored)."""
    ignore = {".omnix"}
    with os.scandir(p) as it:
        for e in it:
            if e.name in ignore:
                continue
            return False
    return True


def _open_mode(p: Path) -> str:
    return "scratch" if _is_empty_dir(p) else "existing"


def _fast_stats(conn: sqlite3.Connection) -> dict[str, int]:
    rowf = conn.execute("SELECT COUNT(DISTINCT file_path) FROM nodes WHERE file_path IS NOT NULL").fetchone()  # noqa: E501
    files = int(rowf[0] or 0) if rowf else 0
    rowfn = conn.execute("SELECT COUNT(*) FROM nodes WHERE type IN ('function','method')").fetchone()  # noqa: E501
    functions = int(rowfn[0] or 0) if rowfn else 0
    rowc = conn.execute("SELECT COUNT(*) FROM nodes WHERE type = 'class'").fetchone()  # noqa: E501
    classes = int(rowc[0] or 0) if rowc else 0
    rowe = conn.execute("SELECT COUNT(*) FROM edges").fetchone()
    edges = int(rowe[0] or 0) if rowe else 0
    rowd = conn.execute("SELECT COUNT(*) FROM nodes WHERE type = 'dark_matter'").fetchone()  # noqa: E501
    dark = int(rowd[0] or 0) if rowd else 0
    rowt = conn.execute("SELECT COUNT(*) FROM edges WHERE relationship = 'ENTANGLED'").fetchone()  # noqa: E501
    ent = int(rowt[0] or 0) if rowt else 0
    return {
        "files": files,
        "functions": functions,
        "classes": classes,
        "edges": edges,
        "dark_matter": dark,
        "entangled": ent,
    }


@dataclass
class Workspace:
    id: str
    root: Path
    mode: str
    store: GraphStore
    ingest_event: asyncio.Event
    _websockets: set[WebSocket] = field(default_factory=set)  # type: ignore[valid-type]
    _last_file_activity: float = field(default_factory=time.time, repr=False)
    _watcher: ProjectWatcher | None = field(default=None, repr=False)
    _parse_bridge: ParserBridge | None = field(default=None, repr=False)
    _stats_loop_task: asyncio.Task[None] | None = field(default=None, repr=False)
    _ingest_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    def mark_activity(self) -> None:
        self._last_file_activity = time.time()

    def is_graph_idle(self, now: float) -> bool:
        return (now - self._last_file_activity) > 2.0

    def stats_dict(self) -> dict[str, int]:
        c = self.store.sqlite_connection()
        return _fast_stats(c)

    def set_watcher(self, w: ProjectWatcher) -> None:
        self._watcher = w

    def set_parser_bridge(self, p: ParserBridge) -> None:
        self._parse_bridge = p

    @property
    def parse_bridge(self) -> ParserBridge | None:
        return self._parse_bridge

    def add_ws(self, ws: WebSocket) -> None:
        self._websockets.add(ws)  # type: ignore[union-attr]

    def remove_ws(self, ws: WebSocket) -> None:
        self._websockets.discard(ws)  # type: ignore[union-attr]

    def register_stats_loop(self, t: asyncio.Task[None] | None) -> None:
        self._stats_loop_task = t

    async def stop(self) -> None:
        if self._stats_loop_task and not self._stats_loop_task.done():
            self._stats_loop_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._stats_loop_task
        if self._watcher is not None:
            self._watcher.stop()
            self._watcher = None
        for ws in list(self._websockets):
            with contextlib.suppress(Exception):
                await ws.close()
        self._websockets.clear()
        with contextlib.suppress(OSError, ValueError):
            self.store.close()
        await remove_session_dir(self.id)


@dataclass
class WorkspaceManager:
    workspaces: dict[str, Workspace] = field(default_factory=dict)
    active_bug_scans: dict[str, str] = field(default_factory=dict)
    _bug_scan_guard: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def get(self, wid: str) -> Workspace | None:
        return self.workspaces.get(wid)

    def put(self, ws: Workspace) -> None:
        self.workspaces[ws.id] = ws

    def remove(self, wid: str) -> None:
        self.workspaces.pop(wid, None)
        with self._bug_scan_guard:
            self.active_bug_scans.pop(wid, None)

    def try_begin_bug_scan(self, wid: str, scan_id: str) -> str | None:
        with self._bug_scan_guard:
            active = self.active_bug_scans.get(wid)
            if active:
                return active
            self.active_bug_scans[wid] = scan_id
            return None

    def finish_bug_scan(self, wid: str, scan_id: str) -> None:
        with self._bug_scan_guard:
            if self.active_bug_scans.get(wid) == scan_id:
                self.active_bug_scans.pop(wid, None)


MANAGER = WorkspaceManager()


def node_row_to_dict(n: NodeRow) -> dict[str, Any]:
    return {
        "id": n.id,
        "name": n.name,
        "type": n.type,
        "file_path": n.file_path,
        "line_start": n.start_line,
        "line_end": n.end_line,
        "metadata": n.metadata or {},
    }


def open_workspace(
    project_path: str,
    store_factory: Callable[[str], GraphStore] = GraphStore,
) -> tuple[Workspace, dict[str, int]]:
    """Validate path (directory), create ``.omnix/`` if needed, return workspace + current stats."""
    p = Path(os.path.realpath(str(project_path)))
    if not p.is_dir():
        raise ValueError("not a directory")
    ensure_project_omnix_dir(p)
    dbp = str(project_graph_db_path(p))
    st = store_factory(dbp)
    mode = _open_mode(p)
    if mode == "scratch":
        cfg = ensure_project_omnix_dir(p) / "config.json"
        if not cfg.is_file():
            cfg.write_text('{"studio": {"version": 1}}', encoding="utf-8")
    wid = str(uuid.uuid4())
    w = Workspace(
        id=wid,
        root=p,
        mode=mode,
        store=st,
        ingest_event=asyncio.Event(),
    )
    ensure_session_artifact(wid)
    stats0 = w.stats_dict()
    return w, stats0
