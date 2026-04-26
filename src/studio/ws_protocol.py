"""WebSocket message types and JSON encoding for OMNIX Studio."""

from __future__ import annotations

import time
from typing import Any, Literal, TypedDict

# --- Server → client payloads ------------------------------------------------


class WsError(Exception):
    """Invalid message *type* or bad payload."""


def _ts() -> float:
    return time.time()


def msg_bootstrap_start(
    workspace_id: str,
    total_files: int,
    mode: Literal["existing", "scratch"],
) -> dict[str, Any]:
    return {
        "type": "bootstrap_start",
        "ts": _ts(),
        "workspace_id": workspace_id,
        "total_files": int(total_files),
        "mode": mode,
    }


def msg_bootstrap_complete(
    duration_ms: int,
    total_nodes: int,
    total_edges: int,
) -> dict[str, Any]:
    return {
        "type": "bootstrap_complete",
        "ts": _ts(),
        "duration_ms": int(duration_ms),
        "total_nodes": int(total_nodes),
        "total_edges": int(total_edges),
    }


def msg_node_added(node: dict[str, Any]) -> dict[str, Any]:
    return {"type": "node_added", "ts": _ts(), "node": node}


def msg_edge_added(edge: dict[str, Any]) -> dict[str, Any]:
    return {"type": "edge_added", "ts": _ts(), "edge": edge}


def msg_node_modified(node_id: str, changes: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": "node_modified",
        "ts": _ts(),
        "node_id": node_id,
        "changes": changes,
    }


def msg_node_removed(node_id: str) -> dict[str, Any]:
    return {"type": "node_removed", "ts": _ts(), "node_id": node_id}


def msg_edge_removed(edge_id: int) -> dict[str, Any]:
    return {"type": "edge_removed", "ts": _ts(), "edge_id": int(edge_id)}


def msg_file_added(path: str) -> dict[str, Any]:
    return {"type": "file_added", "ts": _ts(), "path": path}


def msg_file_removed(path: str) -> dict[str, Any]:
    return {"type": "file_removed", "ts": _ts(), "path": path}


def msg_stats(
    files: int,
    functions: int,
    classes: int,
    edges: int,
    dark_matter: int,
    entangled: int,
) -> dict[str, Any]:
    return {
        "type": "stats",
        "ts": _ts(),
        "files": int(files),
        "functions": int(functions),
        "classes": int(classes),
        "edges": int(edges),
        "dark_matter": int(dark_matter),
        "entangled": int(entangled),
    }


def msg_error(message: str, recoverable: bool) -> dict[str, Any]:
    return {"type": "error", "ts": _ts(), "message": str(message), "recoverable": bool(recoverable)}


def msg_pong(ts: float) -> dict[str, Any]:
    return {"type": "pong", "ts": float(ts)}


ALL_SERVER_TYPES: frozenset[str] = frozenset(
    {
        "bootstrap_start",
        "bootstrap_complete",
        "node_added",
        "edge_added",
        "node_modified",
        "node_removed",
        "edge_removed",
        "file_added",
        "file_removed",
        "stats",
        "error",
        "pong",
    }
)


def validate_serialized(m: dict[str, Any], *, from_server: bool) -> str:
    """Return message type, or raise WsError."""
    t = m.get("type")
    if not isinstance(t, str):
        raise WsError("missing type")
    if from_server and t not in ALL_SERVER_TYPES:
        raise WsError("unknown type")
    return t


# Typed view for tests / frontend ports (optional)
class _BootstrapStart(TypedDict, total=False):
    type: Literal["bootstrap_start"]
    ts: float
    workspace_id: str
    total_files: int
    mode: str
