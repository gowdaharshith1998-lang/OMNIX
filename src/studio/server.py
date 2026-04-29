"""FastAPI Studio server: REST, WebSocket, static SPA (production)."""

from __future__ import annotations

import logging
import os

if os.environ.get("OMNIX_STUDIO_DEBUG") == "1":
    logging.basicConfig(
        level=logging.WARNING, format="%(levelname)s:%(name)s:%(message)s", force=True
    )
    for _noisy in ("watchdog", "watchdog.observers", "watchdog.observers.inotify_buffer"):
        logging.getLogger(_noisy).setLevel(logging.WARNING)
    logging.getLogger("omnix.studio").setLevel(logging.DEBUG)
    _pb = logging.getLogger("omnix.studio.parser_bridge")
    _pb.setLevel(logging.INFO)
    if not _pb.handlers:
        _pb_h = logging.StreamHandler()
        _pb_h.setLevel(logging.INFO)
        _pb_h.setFormatter(
            logging.Formatter("%(levelname)s:%(name)s:%(message)s")
        )
        _pb.addHandler(_pb_h)
        _pb.propagate = False

import asyncio
import contextlib
import json
import time
import hashlib
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import sqlite3
from fastapi import FastAPI, HTTPException, Query, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from src.graph.store import GraphStore, NodeRow
from src.parser import evolution
from src.parser.grammar_detect import detect_for_path
from src.parser.ingest_dispatch import ingest_unified_codebase
from src.omnix_version import __version__
from src.studio.parser_bridge import ParserBridge, broadcast_to_workspace
from src.studio.recent import add_recent, list_recent
from src.studio.watcher import ProjectWatcher
from src.studio.workspace import (
    MANAGER,
    Workspace,
    node_row_to_dict,
    open_workspace,
)
from src.studio.watcher import is_studio_ignored
from src.studio.ws_protocol import (
    msg_bootstrap_complete,
    msg_bootstrap_start,
    msg_edge_added,
    msg_error,
    msg_node_added,
    msg_pong,
    msg_stats,
)

INITIAL_STUDIO_PATH: str | None = None
_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_FRONTEND_DIST = _REPO_ROOT / "src" / "studio" / "frontend" / "dist"


@contextlib.asynccontextmanager
async def _app_lifespan(_app: FastAPI) -> Any:  # noqa: ANN401, RUF029, ASYNC109
    yield
    for w in list(MANAGER.workspaces.values()):
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await w.stop()  # type: ignore[union-attr, misc, no-untyped-def]


app = FastAPI(title="OMNIX Studio", lifespan=_app_lifespan)  # type: ignore[assignment, misc, no-untyped-def]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models
class OpenBody(BaseModel):
    path: str


class CloseBody(BaseModel):
    workspace_id: str = Field(min_length=1)


class FileWriteBody(BaseModel):
    path: str
    content: str = ""


class FilePutBody(BaseModel):
    path: str
    content: str
    expected_last_modified: float = Field(
        description="Mtime of file when read (epoch seconds, float from OS)"
    )


def _row_to_node_public(r: sqlite3.Row) -> NodeRow:
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


def get_node_by_id(st: GraphStore, node_id: str) -> NodeRow | None:
    c = st.sqlite_connection()
    r = c.execute("SELECT * FROM nodes WHERE id = ?", (node_id,)).fetchone()
    if not r:
        return None
    return _row_to_node_public(r)


def _ingest_block(workspace: Workspace) -> None:
    assert isinstance(workspace, Workspace)  # noqa: S101
    evolution.begin_evolution_run()
    try:
        ingest_unified_codebase(
            str(workspace.root), workspace.store, force=False, omnix_version=__version__
        )
    finally:
        with contextlib.suppress(OSError, ValueError, RuntimeError):
            evolution.finalize_evolution_run(workspace.store.sqlite_connection())
    with contextlib.suppress(OSError, ValueError, RuntimeError):
        workspace.store.commit()


async def _start_background_ingest(w: Workspace, loop: asyncio.AbstractEventLoop) -> None:  # noqa: E501
    await loop.run_in_executor(None, _ingest_block, w)
    br = ParserBridge(loop, w)
    w.set_parser_bridge(br)  # type: ignore[union-attr, misc, no-untyped-def]
    obs = ProjectWatcher(
        str(w.root),
        br.on_filesystem,
    )
    obs.start()
    w.set_watcher(obs)  # type: ignore[union-attr, misc, no-untyped-def]
    br.start()  # type: ignore[union-attr, misc, no-untyped-def]
    w.ingest_event.set()  # type: ignore[union-attr, misc, no-untyped-def]


# --- API ---


@app.get("/api/health")
def api_health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@app.get("/api/recent")
def api_recent() -> dict[str, list[dict[str, str]]]:
    return {"recent": list_recent()}


@app.get("/api/studio/initial")
def api_studio_initial() -> dict[str, str | None]:
    envp = (os.environ.get("OMNIX_STUDIO_INITIAL") or "").strip()
    p = (INITIAL_STUDIO_PATH or envp or None)  # type: ignore[has-type, assignment, misc, no-redef, union-attr]
    return {"path": p}  # type: ignore[return-value, no-any-return]


def _parse_receipt_bound(raw: str | None) -> float | None:
    if raw is None or not raw.strip():
        return None
    s = raw.strip()
    with contextlib.suppress(ValueError):
        return float(s)
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(s).timestamp()
    except ValueError:
        raise HTTPException(400, "invalid receipt time bound") from None


def _receipt_source(path: Path, body: dict[str, Any]) -> str:
    stem = path.stem.lower()
    event = str(body.get("event") or body.get("kind") or "").lower()
    if stem.startswith("call_") or "fabric" in event or body.get("call_id") is not None:
        return "fabric"
    if stem.startswith("scan") or event.startswith("vault.scan"):
        return "scan"
    if stem.startswith("evolution_") or "evolution" in event:
        return "evolution"
    return "future"


def _receipt_kind(source: str, body: dict[str, Any]) -> str:
    raw = body.get("event") or body.get("kind") or body.get("type")
    if isinstance(raw, str) and raw:
        return raw
    if source == "fabric":
        return "fabric.call"
    if source == "scan":
        return "vault.scan"
    if source == "evolution":
        return "grammar.evolution"
    return "receipt"


def _receipt_target(body: dict[str, Any]) -> str:
    for key in ("target", "file", "path", "grammar", "grammar_name", "provider", "model"):
        value = body.get(key)
        if isinstance(value, str) and value:
            return value
    provider = body.get("provider")
    model = body.get("model")
    if provider or model:
        return " / ".join(str(x) for x in (provider, model) if x)
    return ""


def _iter_receipts(
    *, since: float | None, until: float | None, limit: int
) -> list[dict[str, Any]]:
    root = (Path.home() / ".omnix" / "receipts").expanduser()
    if not root.is_dir():
        return []
    rows: list[dict[str, Any]] = []
    for path in root.glob("*.json"):
        try:
            st = path.stat()
        except OSError:
            continue
        mtime = float(st.st_mtime)
        if since is not None and mtime < since:
            continue
        if until is not None and mtime > until:
            continue
        try:
            raw = path.read_bytes()
            body0 = json.loads(raw.decode("utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError, UnicodeDecodeError):
            body0 = {}
            raw = b""
        body = body0 if isinstance(body0, dict) else {}
        source = _receipt_source(path, body)
        rows.append(
            {
                "kind": _receipt_kind(source, body),
                "target": _receipt_target(body),
                "hash_prefix": hashlib.sha256(raw).hexdigest()[:12] if raw else "",
                "sig_alg": "ML-DSA-65" if path.with_suffix(".sig").is_file() else "unsigned",
                "mtime_iso": datetime.fromtimestamp(mtime, timezone.utc).isoformat().replace("+00:00", "Z"),
                "source": source,
                "path": str(path),
            }
        )
    rows.sort(key=lambda r: str(r.get("mtime_iso") or ""), reverse=True)
    return rows[:limit]


@app.get("/api/workspace/{workspace_id}/receipts")
def api_workspace_receipts(
    workspace_id: str,
    since: str | None = None,
    until: str | None = None,
    limit: int = 100,
) -> dict[str, list[dict[str, Any]]]:
    w = MANAGER.get(workspace_id)
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    lim = max(1, min(int(limit), 500))
    return {
        "receipts": _iter_receipts(
            since=_parse_receipt_bound(since),
            until=_parse_receipt_bound(until),
            limit=lim,
        )
    }


def _edge_dict(
    eid: int, sid: str, tid: str, rel: str, meta: dict[str, Any] | None
) -> dict[str, Any]:
    return {
        "id": eid,
        "source_id": sid,
        "target_id": tid,
        "relationship": rel,
        "metadata": meta or {},
    }


def _row_edge(r: sqlite3.Row) -> dict[str, Any]:  # noqa: D103
    m = r["metadata"]
    return _edge_dict(
        int(r["id"]),
        str(r["source_id"]),
        str(r["target_id"]),
        str(r["relationship"]),
        json.loads(m) if m else None,
    )


async def _run_bootstrap(websocket: WebSocket, w: Workspace) -> None:
    st = w.store
    c = st.sqlite_connection()
    t0 = time.time()
    rowf = c.execute("SELECT COUNT(*) FROM file_hashes").fetchone()  # noqa: E501
    total_files = int(rowf[0] or 0) if rowf else 0
    n_total = c.execute("SELECT COUNT(*) FROM nodes").fetchone()  # noqa: E501
    n_nodes = int(n_total[0] or 0) if n_total else 0
    e_row = c.execute("SELECT COUNT(*) FROM edges").fetchone()  # noqa: E501
    n_edges = int(e_row[0] or 0) if e_row else 0
    bmode: Any = "scratch" if w.mode == "scratch" else "existing"
    await websocket.send_text(
        json.dumps(msg_bootstrap_start(w.id, max(0, total_files), bmode))
    )
    last_s = 0.0
    for r in c.execute("SELECT * FROM nodes ORDER BY file_path, id"):
        node_r = _row_to_node_public(r)  # noqa: E501
        await websocket.send_text(
            json.dumps(msg_node_added(node_row_to_dict(node_r)))
        )  # noqa: E501
        n = time.time()
        if n - last_s >= 1.0:
            s = w.stats_dict()  # noqa: E501
            await websocket.send_text(
                json.dumps(
                    msg_stats(
                        s["files"],
                        s["functions"],
                        s["classes"],
                        s["edges"],
                        s["dark_matter"],
                        s["entangled"],
                    )
                )  # noqa: E501
            )
            last_s = n
    for r in c.execute("SELECT * FROM edges ORDER BY id"):
        await websocket.send_text(
            json.dumps(  # type: ignore[no-untyped-def, misc, no-any-return, arg-type]
                msg_edge_added(  # noqa: E501
                    _row_edge(r)  # noqa: E501
                )
            )  # noqa: E501
        )
    dur = int(1000 * (time.time() - t0))
    await websocket.send_text(
        json.dumps(msg_bootstrap_complete(dur, n_nodes, n_edges), default=str)  # noqa: E501
    )


@app.post("/api/workspace/open")
async def api_workspace_open(body: OpenBody) -> dict[str, Any]:
    try:
        w, stats0 = open_workspace(body.path)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    add_recent(body.path)
    MANAGER.put(w)
    loop = asyncio.get_running_loop()  # noqa: E501
    asyncio.create_task(_start_background_ingest(w, loop))  # noqa: RUF006
    return {
        "workspace_id": w.id,
        "mode": w.mode,
        "stats": {
            "files": stats0["files"],
            "functions": stats0["functions"],
            "classes": stats0["classes"],
            "edges": stats0["edges"],
        },
    }


@app.post("/api/workspace/close")
async def api_workspace_close(body: CloseBody) -> dict[str, bool]:  # noqa: D103
    w = MANAGER.get(body.workspace_id)
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    await w.stop()  # type: ignore[union-attr, misc, no-untyped-def]
    MANAGER.remove(body.workspace_id)
    return {"closed": True}


def _file_matches_prefix(rel: str, pfx: str) -> bool:
    if not pfx:
        return True
    return rel == pfx or rel.startswith(pfx.rstrip("/") + "/")


def _iter_listable_files(
    root: Path, pfx: str, limit: int
) -> list[dict[str, Any]]:
    root = root.resolve()
    pfx0 = pfx or ""
    out: list[dict[str, Any]] = []
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        try:
            r = f.relative_to(root).as_posix()  # noqa: E501
        except (OSError, ValueError) as e:  # noqa: F841, E501
            continue
        if is_studio_ignored(root, r) or not _file_matches_prefix(r, pfx0):
            continue
        try:  # noqa: E501
            st = f.stat()
        except OSError:
            continue
        out.append(
            {
                "path": r,
                "type": "file",
                "size": st.st_size,
                "modified": st.st_mtime,
            }
        )  # noqa: E501
        if len(out) >= limit:
            break
    return out


_TREE_SKIP_NAMES = {"__pycache__", "node_modules", ".git", ".omnix-cache"}


def _is_tree_skipped(root: Path, rel: str) -> bool:
    parts = [p for p in rel.split("/") if p]
    if any(p.startswith(".") for p in parts):
        return True
    if any(p in _TREE_SKIP_NAMES for p in parts):
        return True
    return is_studio_ignored(root, rel)


def _empty_tree_dir(name: str) -> dict[str, Any]:
    return {"name": name, "type": "dir", "children": []}


def _insert_tree_file(root_node: dict[str, Any], parts: list[str], size: int) -> None:
    cur = root_node
    for part in parts[:-1]:
        children = cur.setdefault("children", [])
        hit = next(
            (
                c
                for c in children
                if isinstance(c, dict) and c.get("name") == part and c.get("type") == "dir"
            ),
            None,
        )
        if hit is None:
            hit = _empty_tree_dir(part)
            children.append(hit)
        cur = hit
    children = cur.setdefault("children", [])
    children.append({"name": parts[-1], "type": "file", "size": int(size)})


def _sort_tree(node: dict[str, Any]) -> None:
    children = node.get("children")
    if not isinstance(children, list):
        return
    children.sort(key=lambda c: (0 if c.get("type") == "dir" else 1, str(c.get("name", ""))))
    for child in children:
        if isinstance(child, dict) and child.get("type") == "dir":
            _sort_tree(child)


def _build_file_tree(root: Path, *, max_depth: int = 6) -> dict[str, Any]:
    root = root.resolve()
    tree = _empty_tree_dir(root.name or root.as_posix())
    for f in root.rglob("*"):
        if not f.is_file():
            continue
        try:
            rel = f.relative_to(root).as_posix()
        except (OSError, ValueError):
            continue
        parts = [p for p in rel.split("/") if p]
        if not parts or len(parts) > max_depth or _is_tree_skipped(root, rel):
            continue
        try:
            size = f.stat().st_size
        except OSError:
            size = 0
        _insert_tree_file(tree, parts, int(size))
    _sort_tree(tree)
    return tree


@app.get("/api/workspace/{workspace_id}/files")
def api_list_files(  # noqa: D103
    workspace_id: str,
    prefix: str = "",
    limit: int = 100,
) -> dict[str, list[dict[str, Any]]]:  # noqa: E501
    w = MANAGER.get(workspace_id)  # noqa: E501
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    lim = max(1, min(limit, 200))
    return {
        "files": _iter_listable_files(  # noqa: E501
            w.root,  # type: ignore[no-untyped-def, misc, no-any-return, arg-type, union-attr, misc]
            prefix,  # noqa: E501
            lim,  # noqa: E501
        )
    }


@app.get("/api/workspace/{workspace_id}/files/tree")
def api_files_tree(workspace_id: str) -> dict[str, dict[str, Any]]:
    w = MANAGER.get(workspace_id)
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    return {"tree": _build_file_tree(w.root)}


@app.post("/api/workspace/{workspace_id}/file")
async def api_create_file(  # noqa: D103
    workspace_id: str,
    body: FileWriteBody,
) -> dict[str, Any]:  # noqa: E501
    w = MANAGER.get(workspace_id)  # noqa: E501
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    rel = body.path.replace("\\", "/").lstrip("/")
    p = w.root / rel
    p.parent.mkdir(parents=True, exist_ok=True)  # noqa: E501
    p.write_text(body.content, encoding="utf-8", newline="")  # noqa: E501, WPS
    return {"created": True, "path": rel}  # noqa: E501


@app.get("/api/workspace/{workspace_id}/file")
def api_get_file(  # noqa: D103
    workspace_id: str,
    path: str = Query(""),
) -> dict[str, Any]:  # noqa: E501
    w = MANAGER.get(workspace_id)  # noqa: E501
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    if not path:
        raise HTTPException(400, "path required")
    p = w.root / path
    if not p.is_file():
        raise HTTPException(404, "file not found")
    raw = p.read_text(encoding="utf-8", errors="replace")
    mtime = 0.0
    with contextlib.suppress(OSError, ValueError):
        mtime = p.stat().st_mtime
    d = detect_for_path(p)
    lang = (d.grammar_name or d.inferred_lang or "text") or "text"  # noqa: E501
    return {  # noqa: E501
        "path": path,
        "content": raw,
        "last_modified": mtime,
        "language": str(lang),  # noqa: E501
    }


def _mtime_mismatch(
    a: float, b: float, *, eps: float = 0.5e-2
) -> bool:
    return abs(float(a) - float(b)) > eps


@app.put("/api/workspace/{workspace_id}/file")
async def api_put_file(  # noqa: D103
    workspace_id: str,
    body: FilePutBody,
) -> dict[str, Any]:
    w = MANAGER.get(workspace_id)  # noqa: E501
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    rel = body.path.replace("\\", "/").lstrip("/")
    p = w.root / rel
    if not p.is_file():
        raise HTTPException(404, "file not found")
    try:  # noqa: E501, SIM, E501
        cur = float(p.stat().st_mtime)  # noqa: E501, WPS, E501, WPS
    except (OSError, ValueError, RuntimeError):
        cur = 0.0
    if _mtime_mismatch(float(cur), float(body.expected_last_modified)):
        raise HTTPException(409, "stale: file changed on disk")
    p.write_text(body.content, encoding="utf-8", newline="")
    nm2 = 0.0
    with contextlib.suppress(OSError, ValueError, RuntimeError, TypeError):
        nm2 = float(p.stat().st_mtime)  # noqa: E501
    return {
        "written": True,  # noqa: E501
        "new_last_modified": float(nm2),  # noqa: E501, WPS
    }


def _node_refs(
    c: sqlite3.Connection, node_id: str, *, as_target: bool
) -> list[dict[str, str | None]]:  # noqa: D103, E501
    """Callers: edges into *node*; callees: edges from *node* (CALLS only)."""
    if as_target:  # noqa: E501
        sub = (  # noqa: E501
            "SELECT source_id FROM edges WHERE target_id = ? "  # noqa: E501
            "AND relationship = 'CALLS' LIMIT 50"  # noqa: E501
        )
    else:  # noqa: E501
        sub = (  # noqa: E501
            "SELECT target_id FROM edges WHERE source_id = ? "  # noqa: E501
            "AND relationship = 'CALLS' LIMIT 50"  # noqa: E501
        )
    out: list[dict[str, str | None]] = []
    for r in c.execute(  # noqa: E501
        f"SELECT n.id, n.name, n.type FROM nodes n WHERE n.id IN ({sub})",  # noqa: S608, E501
        (node_id,),
    ):
        out.append(
            {
                "id": str(r[0]),
                "name": str(r[1]) if r[1] is not None else None,
                "type": str(r[2]) if r[2] is not None else None,
            }
        )
    return out


@app.get("/api/workspace/{workspace_id}/node/{node_id}")
def api_get_node(  # noqa: D103
    workspace_id: str,
    node_id: str,
) -> dict[str, Any]:  # noqa: E501
    w = MANAGER.get(workspace_id)  # noqa: E501
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    st = w.store
    n0 = get_node_by_id(st, node_id)  # noqa: E501
    if n0 is None:  # noqa: E501
        raise HTTPException(404, "node not found")
    c0 = st.sqlite_connection()
    return {
        "node": {
            "id": n0.id,  # noqa: E501
            "name": n0.name,
            "type": n0.type,
            "file_path": n0.file_path,
            "line_start": n0.start_line,
            "line_end": n0.end_line,
            "metadata": n0.metadata or {},
        },
        "callers": _node_refs(c0, n0.id, as_target=True),
        "callees": _node_refs(c0, n0.id, as_target=False),
        "file_path": n0.file_path,
        "line_start": n0.start_line,
        "line_end": n0.end_line,
    }


@app.get("/api/workspace/{workspace_id}/search")
def api_search(
    workspace_id: str,
    q: str = "",
    kind: str = "all",
    limit: int = 50,
) -> dict[str, list[dict[str, Any]]]:
    w = MANAGER.get(workspace_id)
    if w is None:
        raise HTTPException(404, "unknown workspace_id")
    query = q.strip()
    if not query:
        return {"results": []}
    if kind not in {"symbol", "file", "all"}:
        raise HTTPException(400, "kind must be symbol, file, or all")
    lim = max(1, min(int(limit), 100))
    like = f"%{query.lower()}%"
    types: tuple[str, ...]
    if kind == "file":
        types = ("file",)
    elif kind == "symbol":
        types = ("function", "method", "class")
    else:
        types = ("file", "function", "method", "class")
    ph = ",".join("?" * len(types))
    sql = (
        "SELECT name, type, file_path, start_line FROM nodes "
        f"WHERE type IN ({ph}) AND "
        "(lower(name) LIKE ? OR lower(file_path) LIKE ?) "
        "ORDER BY file_path, start_line, name LIMIT ?"
    )
    c = w.store.sqlite_connection()
    rows: list[dict[str, Any]] = []
    for row in c.execute(sql, (*types, like, like, lim)):
        typ = str(row["type"])
        rows.append(
            {
                "kind": "file" if typ == "file" else "symbol",
                "name": str(row["name"] or ""),
                "path": str(row["file_path"] or ""),
                "line": int(row["start_line"] or 0),
                "snippet": "",
            }
        )
    return {"results": rows}

async def _stats_ticker(w: Workspace, stop: asyncio.Event) -> None:
    while w._websockets:  # type: ignore[union-attr, misc, no-untyped-def]
        if stop.is_set():
            return
        try:
            await asyncio.wait_for(stop.wait(), timeout=0.5)
        except asyncio.CancelledError:
            raise
        except (asyncio.TimeoutError, OSError):
            s = w.stats_dict()
            with contextlib.suppress(Exception):
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
        else:
            return


@app.websocket("/ws/workspace/{workspace_id}")
async def ws_workspace(websocket: WebSocket, workspace_id: str) -> None:
    w = MANAGER.get(workspace_id)
    if w is None:
        await websocket.close(code=1008)
        return
    await websocket.accept()
    w.add_ws(websocket)  # type: ignore[union-attr, misc, no-untyped-def]
    stop = asyncio.Event()
    t_stats = asyncio.create_task(_stats_ticker(w, stop), name="studio-stats")
    try:
        try:
            first = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
        except asyncio.TimeoutError:
            return
        try:
            d0 = json.loads(first) if first else {}
        except json.JSONDecodeError:
            await websocket.send_text(json.dumps(msg_error("invalid JSON", True)))
            return
        if d0.get("type") != "subscribe" or d0.get("workspace_id") != workspace_id:
            await websocket.send_text(
                json.dumps(
                    msg_error("expected subscribe with matching workspace_id", True)
                )
            )
            return
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(w.ingest_event.wait(), timeout=600.0)  # type: ignore[union-attr, misc, no-untyped-def]
        await _run_bootstrap(websocket, w)
        while True:
            try:
                raw = await asyncio.wait_for(websocket.receive_text(), timeout=30.0)
            except (asyncio.TimeoutError,):
                continue
            try:
                d2 = json.loads(raw)
            except json.JSONDecodeError:
                continue
            if d2.get("type") == "ping":
                await websocket.send_text(
                    json.dumps(msg_pong(float(d2.get("ts", 0.0))))
                )
    except WebSocketDisconnect:
        pass
    except asyncio.CancelledError:
        raise
    finally:
        stop.set()
        t_stats.cancel()
        with contextlib.suppress(asyncio.CancelledError, Exception):
            await t_stats
        w.remove_ws(websocket)  # type: ignore[union-attr, misc, no-untyped-def]


if (_FRONTEND_DIST / "assets").is_dir():
    app.mount(
        "/assets",
        StaticFiles(directory=str(_FRONTEND_DIST / "assets")),
        name="studio-assets",
    )


@app.get("/", response_model=None)  # noqa: E501
def spa_index() -> FileResponse | JSONResponse:  # noqa: D103
    idx = _FRONTEND_DIST / "index.html"
    if idx.is_file():
        return FileResponse(str(idx))
    return JSONResponse(
        {"detail": "Build frontend: cd src/studio/frontend && npm run build"},
        status_code=200,
    )


def run(
    *,
    project_path: str | None = None,
    host: str = "127.0.0.1",
    port: int | None = None,
) -> None:  # noqa: D103
    import uvicorn  # noqa: WPS433

    global INITIAL_STUDIO_PATH  # noqa: PLW0603
    p = int((os.environ.get("OMNIX_STUDIO_PORT") or "7778").strip() or 7778)
    if port is not None:
        p = int(port)
    if project_path is not None:
        INITIAL_STUDIO_PATH = str(Path(project_path).resolve())
    else:
        INITIAL_STUDIO_PATH = None
    uvicorn.run(app, host=host, port=p)
