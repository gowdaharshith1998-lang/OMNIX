"""Export graph from SQLite to JSON for the web viewer."""

from __future__ import annotations

import json
from typing import Any

from omnix.graph.store import GraphStore

_TYPE_COLORS: dict[str, str] = {
    "file": "#3b82f6",
    "function": "#4ade80",
    "class": "#a855f7",
    "method": "#22d3ee",
    "import": "#f97316",
    "dark_matter": "#8b5cf6",
    # Company-brain entity types (slice-19): code (cyan), people (amber), decision (purple),
    # thread (lavender), ticket (orange), document (blue-gray), process (teal-green).
    "code": "#5eead4",
    "people": "#fbbf24",
    "decision": "#d8b4fe",
    "thread": "#a5b4fc",
    "ticket": "#fb923c",
    "document": "#5fa3ff",
    "process": "#34d399",
}

FALLBACK_COLOR = "#9ca3af"


def color_for_type(node_type: str) -> str:
    """Return the registered color for a node type, or the fallback for unknowns.

    Used by exporters and by the WebSocket `node_added` payload builder to
    stamp a `color` field that the frontend can read directly without
    having to know the palette mapping itself.
    """
    return _TYPE_COLORS.get(node_type, FALLBACK_COLOR)


def export_json(store: GraphStore, out_path: str) -> dict[str, Any]:
    store.commit()
    nodes_out: list[dict[str, Any]] = []
    for n in store.iter_all_nodes():
        line = n.start_line if n.start_line is not None else 0
        nodes_out.append(
            {
                "id": n.id,
                "name": n.name,
                "type": n.type,
                "file": n.file_path or "",
                "line": line,
                "val": max(1, n.complexity),
                "color": color_for_type(n.type),
            }
        )

    links_out: list[dict[str, str]] = []
    for e in store.iter_all_edges():
        links_out.append(
            {
                "source": e.source_id,
                "target": e.target_id,
                "type": e.relationship,
            }
        )

    counts: dict[str, int] = {
        "files": 0,
        "functions": 0,
        "classes": 0,
        "methods": 0,
        "imports": 0,
        "dark_matter": 0,
        "entangled": 0,
        "edges": len(links_out),
    }
    for n in nodes_out:
        t = n["type"]
        if t == "file":
            counts["files"] += 1
        elif t == "function":
            counts["functions"] += 1
        elif t == "class":
            counts["classes"] += 1
        elif t == "method":
            counts["methods"] += 1
        elif t == "import":
            counts["imports"] += 1
        elif t == "dark_matter":
            counts["dark_matter"] += 1
    for e in links_out:
        if e.get("type") == "ENTANGLED":
            counts["entangled"] += 1

    payload = {"nodes": nodes_out, "links": links_out, "stats": counts}
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(payload, f)
    return payload
