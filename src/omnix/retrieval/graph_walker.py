"""Deterministic typed-edge graph traversal."""

from __future__ import annotations

from collections import deque

from omnix.graph.store import GraphStore

EDGE_ALIASES = {
    "COPIES": {"COPIES", "copy", "copies"},
    "CALLS": {"CALLS", "call", "calls"},
    "PERFORMS": {"PERFORMS", "perform", "performs"},
    "READS": {"READS", "reads_file", "reads"},
    "WRITES": {"WRITES", "writes_file", "writes"},
    "DEFINES": {"DEFINES", "defines", "moves_to"},
    "INVOKES": {"INVOKES", "invokes"},
}


def walk_from(
    graph_store: GraphStore,
    seed_node_id: str,
    edge_types: list[str],
    max_depth: int = 4,
    max_nodes: int = 200,
) -> list[tuple[str, int]]:
    allowed = _allowed(edge_types)
    conn = graph_store.sqlite_connection()
    out: list[tuple[str, int]] = []
    seen = {seed_node_id}
    queue: deque[tuple[str, int]] = deque([(seed_node_id, 0)])
    while queue and len(out) < max_nodes:
        current, depth = queue.popleft()
        if depth >= max_depth:
            continue
        rows = conn.execute(
            """
            SELECT target_id, relationship FROM edges
            WHERE source_id = ?
            UNION ALL
            SELECT source_id, relationship FROM edges
            WHERE target_id = ?
            """,
            (current, current),
        ).fetchall()
        for row in sorted(rows, key=lambda r: (str(r["target_id"]), str(r["relationship"]))):
            rel = str(row["relationship"])
            nxt = str(row["target_id"])
            if rel not in allowed or nxt in seen:
                continue
            seen.add(nxt)
            out.append((nxt, depth + 1))
            queue.append((nxt, depth + 1))
            if len(out) >= max_nodes:
                break
    return out


def _allowed(edge_types: list[str]) -> set[str]:
    allowed: set[str] = set()
    for edge_type in edge_types:
        allowed |= EDGE_ALIASES.get(edge_type, {edge_type})
    return allowed
