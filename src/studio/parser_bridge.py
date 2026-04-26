"""Watched paths → re-parse, graph delta, WebSocket broadcast. Single async queue per workspace."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any

import sqlite3

from src.graph.store import EdgeRow, GraphStore, NodeRow
from src.parser import evolution
from src.parser.ingest_dispatch import default_parse_mode, ingest_one_path
from src.studio.delta import compute_file_delta
from src.studio.ws_protocol import (
    msg_edge_added,
    msg_edge_removed,
    msg_file_added,
    msg_file_removed,
    msg_node_added,
    msg_node_modified,
    msg_node_removed,
    msg_stats,
)
from src.studio.watcher import is_studio_ignored
from src.studio.workspace import node_row_to_dict, Workspace

if TYPE_CHECKING:
    from starlette.websockets import WebSocket

_LOG = logging.getLogger("omnix.studio.parser_bridge")


def _row_to_node(r: sqlite3.Row) -> NodeRow:
    m = r["metadata"]
    return NodeRow(
        id=str(r["id"]),
        name=str(r["name"]),
        type=str(r["type"]),
        file_path=str(r["file_path"]) if r["file_path"] is not None else None,
        start_line=r["start_line"],
        end_line=r["end_line"],
        complexity=int(r["complexity"] or 0),
        metadata=json.loads(m) if m else None,
    )


def _row_to_edge(r: sqlite3.Row) -> EdgeRow:
    m = r["metadata"]
    return EdgeRow(
        id=int(r["id"]),
        source_id=str(r["source_id"]),
        target_id=str(r["target_id"]),
        relationship=str(r["relationship"]),
        metadata=json.loads(m) if m else None,
    )


def _list_nodes_in_file(conn: sqlite3.Connection, file_path: str) -> list[NodeRow]:
    return [
        _row_to_node(r)
        for r in conn.execute("SELECT * FROM nodes WHERE file_path = ?", (file_path,))
    ]


def _list_edges_for_nodes(conn: sqlite3.Connection, nids: set[str]) -> list[EdgeRow]:
    if not nids:
        return []
    ph = ",".join("?" * len(nids))
    q = f"SELECT * FROM edges WHERE source_id IN ({ph}) OR target_id IN ({ph})"  # noqa: S608
    args: list[str] = list(nids) + list(nids)
    return [_row_to_edge(r) for r in conn.execute(q, args)]


def _edge_to_msg(e: EdgeRow) -> dict[str, Any]:
    return {
        "id": e.id,
        "source_id": e.source_id,
        "target_id": e.target_id,
        "relationship": e.relationship,
        "metadata": e.metadata or {},
    }


async def broadcast_to_workspace(workspace: Workspace, m: dict[str, Any]) -> None:
    raw = json.dumps(m, default=str)
    t = m.get("type", "?")
    nsubs = len(workspace._websockets)  # type: ignore[attr-defined]
    _LOG.debug("broadcast: type=%s subscribers=%d", t, nsubs)
    dead: list[WebSocket] = []
    for w in list(workspace._websockets):  # type: ignore[attr-defined]
        try:
            await w.send_text(raw)  # type: ignore[union-attr, misc]
        except Exception:  # noqa: BLE001
            dead.append(w)
    for w in dead:
        with contextlib.suppress(Exception):
            workspace.remove_ws(w)  # type: ignore[union-attr, misc]


class ParserBridge:
    """100ms debounced filesystem → asyncio queue (serialized by lock) → ingest + delta + WS."""

    def __init__(self, loop: asyncio.AbstractEventLoop, workspace: Workspace) -> None:
        self._loop = loop
        self._w = workspace
        self._q: asyncio.Queue[str] = asyncio.Queue()
        self._pending: set[str] = set()
        self._handle: Any = None
        self._run_task: asyncio.Task[None] | None = None

    def on_filesystem(self, relp: str, _event_kind: str) -> None:  # noqa: ARG002
        if is_studio_ignored(self._w.root, relp):
            return
        with contextlib.suppress(Exception):
            self._loop.call_soon_threadsafe(self._deb, relp)

    def _deb(self, relp: str) -> None:
        self._pending.add(relp)
        if self._handle is not None:
            self._handle.cancel()  # type: ignore[union-attr, misc]
        self._handle = self._loop.call_later(0.1, self._flush)  # type: ignore[assignment, misc]

    def _flush(self) -> None:
        self._handle = None
        to_send = list(self._pending)
        self._pending.clear()
        for relp in to_send:
            with contextlib.suppress(asyncio.QueueFull, RuntimeError):
                _LOG.debug("bridge enqueue: %s", relp)
                self._q.put_nowait(relp)

    def start(self) -> None:
        if self._run_task is not None and not self._run_task.done():
            return
        self._run_task = asyncio.create_task(self._pump(), name="studio-bridge-pump")

    async def _pump(self) -> None:
        while True:
            try:
                relp = await self._q.get()
            except asyncio.CancelledError:
                raise
            _LOG.debug("bridge dequeue: %s", relp)
            try:
                await self._process_one(relp)
            except Exception:  # noqa: BLE001
                _LOG.exception("bridge process %s", relp)

    async def _process_one(self, relp: str) -> None:
        _LOG.debug("parse bridge: processing %s", relp)
        async with self._w._ingest_lock:  # type: ignore[attr-defined]
            w = self._w
            root = w.root
            full = (root / relp)
            st = w.store
            c = st.sqlite_connection()
            with contextlib.suppress(OSError):
                exists = full.exists()
            if not exists:
                await _handle_file_deleted(w, c, relp, st)  # type: ignore[no-untyped-def]
                return
            if not full.is_file():
                return
            b = full.read_bytes()
            mtime = 0.0
            with contextlib.suppress(OSError):
                mtime = full.stat().st_mtime
            sha = hashlib.sha256(b).hexdigest()
            existing = st.get_file_hash_row(relp)
            if (
                existing
                and str(existing[0]) == sha
                and abs(float(existing[1]) - mtime) < 1e-6
            ):
                return
            old_nodes = _list_nodes_in_file(c, relp)
            oids = {n.id for n in old_nodes}
            old_edges = _list_edges_for_nodes(c, oids) if oids else []
            evolution.begin_evolution_run()
            t_err, _g = ingest_one_path(
                st, root, full, parse_mode=default_parse_mode(), skip_tracker=None
            )
            if t_err is not None and t_err in ("error", "unknown_extension", "no_grammar", "binary"):
                _LOG.debug("ingest_one_path %s: %s", relp, t_err)
            with contextlib.suppress(OSError, ValueError, RuntimeError):
                st.commit()
            with contextlib.suppress(OSError, ValueError, RuntimeError):
                evolution.finalize_evolution_run(st.sqlite_connection())
            with contextlib.suppress(OSError, ValueError, RuntimeError):
                st.commit()
            new_nodes = _list_nodes_in_file(c, relp)
            nids = {n.id for n in new_nodes}
            new_edges = _list_edges_for_nodes(c, nids) if nids else []
            d = compute_file_delta(
                relp, old_nodes, new_nodes, old_edges, new_edges
            )
            w.mark_activity()
            if not old_nodes:
                await broadcast_to_workspace(w, msg_file_added(relp))
            for eid in sorted(d.get("removed_edge_ids") or []):
                with contextlib.suppress(TypeError, ValueError):
                    await broadcast_to_workspace(w, msg_edge_removed(int(eid)))
            for nid in d.get("removed_node_ids") or []:
                await broadcast_to_workspace(w, msg_node_removed(str(nid)))
            for mo in d.get("node_modified") or []:
                with contextlib.suppress(TypeError, KeyError):
                    await broadcast_to_workspace(
                        w, msg_node_modified(
                            str(mo["node_id"]),
                            {k: v for k, v in (mo.get("changes") or {}).items()},
                        )
                    )
            for n in d.get("added_nodes") or []:
                await broadcast_to_workspace(w, msg_node_added(node_row_to_dict(n)))
            for e in d.get("added_edges") or []:
                await broadcast_to_workspace(w, msg_edge_added(_edge_to_msg(e)))
            ncount, ecount = len(new_nodes), len(new_edges)
            with contextlib.suppress(OSError, ValueError, RuntimeError):
                st.set_file_hash(relp, sha, mtime, node_count=ncount, edge_count=ecount)  # noqa: E501
            with contextlib.suppress(OSError, ValueError, RuntimeError):
                st.commit()
            s = w.stats_dict()
            await broadcast_to_workspace(
                w,
                msg_stats(
                    s["files"],
                    s["functions"],
                    s["classes"],
                    s["edges"],
                    s["dark_matter"],
                    s["entangled"],
                ),
            )


async def _handle_file_deleted(
    w: Workspace, c: sqlite3.Connection, relp: str, store: GraphStore
) -> None:
    oldn = _list_nodes_in_file(c, relp)
    nset = {n.id for n in oldn}
    oedges = _list_edges_for_nodes(c, nset) if nset else []
    store.delete_graph_rows_for_file_path(relp)
    with contextlib.suppress(OSError, ValueError, RuntimeError):
        store.delete_file_hash(relp)
    with contextlib.suppress(OSError, ValueError, RuntimeError):
        store.commit()
    w.mark_activity()
    await broadcast_to_workspace(w, msg_file_removed(relp))
    for e in oedges:
        await broadcast_to_workspace(w, msg_edge_removed(int(e.id)))
    for n in oldn:
        await broadcast_to_workspace(w, msg_node_removed(n.id))
    s = w.stats_dict()
    await broadcast_to_workspace(
        w,
        msg_stats(
            s["files"],
            s["functions"],
            s["classes"],
            s["edges"],
            s["dark_matter"],
            s["entangled"],
        ),
    )
