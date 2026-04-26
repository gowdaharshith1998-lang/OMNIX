"""Export graph from SQLite to JSON for the web viewer."""

from __future__ import annotations

import json
from typing import Any

from src.graph.store import GraphStore

_TYPE_COLORS: dict[str, str] = {
    "file": "#3b82f6",
    "function": "#4ade80",
    "class": "#a855f7",
    "method": "#22d3ee",
    "import": "#f97316",
    "dark_matter": "#8b5cf6",
}


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
                "color": _TYPE_COLORS.get(n.type, "#94a3b8"),
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
