"""Watched paths → re-parse, graph delta, WebSocket broadcast. Single async queue per workspace."""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import json
import logging
import sqlite3
from typing import TYPE_CHECKING, Any

from omnix.graph.store import EdgeRow, GraphStore, NodeRow
from omnix.parser import evolution
from omnix.parser.ingest_dispatch import default_parse_mode, ingest_one_path
from omnix.studio.delta import compute_file_delta
from omnix.studio.watcher import is_studio_ignored
from omnix.studio.workspace import Workspace, node_row_to_dict
from omnix.studio.ws_protocol import (
    msg_edge_added,
    msg_edge_removed,
    msg_file_added,
    msg_file_removed,
    msg_node_added,
    msg_node_modified,
    msg_node_removed,
    msg_stats,
)

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


def _sha_short(sha: str, n: int = 12) -> str:
    return sha[:n] if len(sha) >= n else sha


def _delta_nonempty(d: dict[str, Any]) -> bool:
    return bool(
        (d.get("added_nodes") or [])
        or (d.get("removed_node_ids") or [])
        or (d.get("node_modified") or [])
        or (d.get("added_edges") or [])
        or (d.get("removed_edge_ids") or [])
    )


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


async def _broadcast_logged(
    workspace: Workspace, m: dict[str, Any], relp: str
) -> None:
    nws = len(workspace._websockets)  # type: ignore[attr-defined]
    mt = m.get("type")
    _LOG.info(
        "broadcast type=%s path=%s ws_count=%d",
        mt,
        relp,
        nws,
        extra={
            "type": mt,
            "path": relp,
            "ws_count": nws,
        },
    )
    await broadcast_to_workspace(workspace, m)


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
            _LOG.debug(
                "debounce_reset",
                extra={
                    "path": relp,
                    "pending_count": len(self._pending),
                },
            )
        self._handle = self._loop.call_later(0.1, self._flush)  # type: ignore[assignment, misc]

    def _flush(self) -> None:
        self._handle = None
        to_send = list(self._pending)
        self._pending.clear()
        _LOG.debug("flush", extra={"paths": list(to_send)})
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
                _LOG.exception("pump_exception", extra={"path": relp})

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
                _LOG.info(
                    "hash_skip path=%s sha=%s mtime=%s row_sha=%s row_mtime=%s",
                    relp,
                    _sha_short(sha),
                    mtime,
                    _sha_short(str(existing[0])),
                    float(existing[1]),
                    extra={
                        "path": relp,
                        "sha": _sha_short(sha),
                        "mtime": mtime,
                        "row_sha": _sha_short(str(existing[0])),
                        "row_mtime": float(existing[1]),
                    },
                )
                return
            old_nodes = _list_nodes_in_file(c, relp)
            oids = {n.id for n in old_nodes}
            old_edges = _list_edges_for_nodes(c, oids) if oids else []
            evolution.begin_evolution_run()
            t_err, _g = ingest_one_path(
                st, root, full, parse_mode=default_parse_mode(), skip_tracker=None
            )
            if t_err is not None:
                result_s = f"{t_err}:{_g}"[:200]
                _LOG.warning(
                    "ingest_skip_or_error path=%s result=%s",
                    relp,
                    result_s,
                    extra={"path": relp, "result": result_s},
                )
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
            _LOG.info(
                "delta_computed path=%s added_nodes=%d modified_nodes=%d "
                "removed_node_ids=%d added_edges=%d removed_edge_ids=%d",
                relp,
                len(d.get("added_nodes") or []),
                len(d.get("node_modified") or []),
                len(d.get("removed_node_ids") or []),
                len(d.get("added_edges") or []),
                len(d.get("removed_edge_ids") or []),
                extra={
                    "path": relp,
                    "added_nodes": len(d.get("added_nodes") or []),
                    "modified_nodes": len(d.get("node_modified") or []),
                    "removed_node_ids": len(d.get("removed_node_ids") or []),
                    "added_edges": len(d.get("added_edges") or []),
                    "removed_edge_ids": len(d.get("removed_edge_ids") or []),
                },
            )
            w.mark_activity()
            if not old_nodes:
                await _broadcast_logged(w, msg_file_added(relp), relp)
            for eid in sorted(d.get("removed_edge_ids") or []):
                with contextlib.suppress(TypeError, ValueError):
                    await _broadcast_logged(w, msg_edge_removed(int(eid)), relp)
            for nid in d.get("removed_node_ids") or []:
                await _broadcast_logged(w, msg_node_removed(str(nid)), relp)
            for mo in d.get("node_modified") or []:
                with contextlib.suppress(TypeError, KeyError):
                    await _broadcast_logged(
                        w,
                        msg_node_modified(
                            str(mo["node_id"]),
                            {k: v for k, v in (mo.get("changes") or {}).items()},
                        ),
                        relp,
                    )
            for n in d.get("added_nodes") or []:
                await _broadcast_logged(w, msg_node_added(node_row_to_dict(n)), relp)
            for e in d.get("added_edges") or []:
                await _broadcast_logged(w, msg_edge_added(_edge_to_msg(e)), relp)
            if (
                not _delta_nonempty(d)
                and old_nodes
                and new_nodes
                and existing is not None
                and str(existing[0]) != sha
            ):
                _LOG.info(
                    "synthetic_node_modified path=%s reason=content_changed_graph_snapshot_unchanged",
                    relp,
                    extra={"path": relp},
                )
                prefer = ("function", "method", "class")
                target = next((n for n in new_nodes if n.type in prefer), None)
                if target is None:
                    target = new_nodes[0]
                await _broadcast_logged(
                    w,
                    msg_node_modified(str(target.id), {}),
                    relp,
                )
            ncount, ecount = len(new_nodes), len(new_edges)
            with contextlib.suppress(OSError, ValueError, RuntimeError):
                st.set_file_hash(relp, sha, mtime, node_count=ncount, edge_count=ecount)  # noqa: E501
            with contextlib.suppress(OSError, ValueError, RuntimeError):
                st.commit()
            s = w.stats_dict()
            await _broadcast_logged(
                w,
                msg_stats(
                    s["files"],
                    s["functions"],
                    s["classes"],
                    s["edges"],
                    s["dark_matter"],
                    s["entangled"],
                ),
                relp,
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
    await _broadcast_logged(w, msg_file_removed(relp), relp)
    for e in oedges:
        await _broadcast_logged(w, msg_edge_removed(int(e.id)), relp)
    for n in oldn:
        await _broadcast_logged(w, msg_node_removed(n.id), relp)
    s = w.stats_dict()
    await _broadcast_logged(
        w,
        msg_stats(
            s["files"],
            s["functions"],
            s["classes"],
            s["edges"],
            s["dark_matter"],
            s["entangled"],
        ),
        relp,
    )
