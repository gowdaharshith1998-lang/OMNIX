"""Graph delta between two snapshots of nodes/edges (Studio live updates)."""

from __future__ import annotations

import json
import logging
from typing import Any

_LOG = logging.getLogger("omnix.studio.delta")

from omnix.graph.store import EdgeRow, NodeRow

_NODE_KEYS: tuple[str, ...] = ("id", "name", "type", "file_path", "start_line", "end_line", "complexity", "metadata")


def _node_sig(n: NodeRow) -> dict[str, Any]:
    m = n.metadata
    m_norm = None if m is None else json.loads(json.dumps(m, sort_keys=True))
    return {
        "id": n.id,
        "name": n.name,
        "type": n.type,
        "file_path": n.file_path,
        "start_line": n.start_line,
        "end_line": n.end_line,
        "complexity": n.complexity,
        "metadata": m_norm,
    }


def _edge_sig(e: EdgeRow) -> tuple[str, str, str, str | None]:
    m = e.metadata
    m_raw = None if m is None else json.dumps(m, sort_keys=True)
    return (e.source_id, e.target_id, e.relationship, m_raw)


def compute_file_delta(
    rel_path: str,
    old_nodes: list[NodeRow],
    new_nodes: list[NodeRow],
    old_edges: list[EdgeRow],
    new_edges: list[EdgeRow],
) -> dict[str, Any]:
    """
    Returns dict with:
      rel_path, added_nodes, removed_node_ids, modified (list of {node_id, changes})
      added_edges, removed_edge_ids, modified_edges
    """
    o_by: dict[str, NodeRow] = {n.id: n for n in old_nodes if n.id}
    n_by: dict[str, NodeRow] = {n.id: n for n in new_nodes if n.id}
    o_ids, n_ids = set(o_by), set(n_by)
    added_ids = n_ids - o_ids
    removed_ids = o_ids - n_ids
    inter = o_ids & n_ids
    modified: list[dict[str, Any]] = []
    for i in inter:
        a, b = o_by[i], n_by[i]
        sa, sb = _node_sig(a), _node_sig(b)
        if sa == sb:
            continue
        changes: dict[str, Any] = {}
        for k in _NODE_KEYS:
            if k == "id":
                continue
            if sa.get(k) != sb.get(k):
                changes[k] = {"old": sa.get(k), "new": sb.get(k)}
        if changes:
            modified.append({"node_id": i, "changes": changes})

    added_nodes = [n_by[i] for i in sorted(added_ids)]
    o_e: dict[tuple[str, str, str, str | None], int] = {}
    for e in old_edges:
        o_e[_edge_sig(e)] = e.id
    n_e: dict[tuple[str, str, str, str | None], int] = {}
    for e in new_edges:
        n_e[_edge_sig(e)] = e.id
    osig, nsig = set(o_e), set(n_e)
    add_e_s = nsig - osig
    rem_e_s = osig - nsig
    added_edges = [e for e in new_edges if _edge_sig(e) in add_e_s]
    removed_edge_ids = [o_e[s] for s in rem_e_s]
    _LOG.debug(
        "delta: %s nodes +%d -%d mod %d edges +%d -%d",
        rel_path,
        len(added_ids),
        len(removed_ids),
        len(modified),
        len(added_edges),
        len(removed_edge_ids),
    )
    return {
        "rel_path": rel_path,
        "added_nodes": added_nodes,
        "removed_node_ids": sorted(removed_ids),
        "node_modified": modified,
        "added_edges": added_edges,
        "removed_edge_ids": sorted(removed_edge_ids),
    }
