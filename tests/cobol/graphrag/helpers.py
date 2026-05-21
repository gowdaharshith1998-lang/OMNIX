from __future__ import annotations

import json
from pathlib import Path

from omnix.graph.store import GraphStore


def graph(tmp_path: Path) -> GraphStore:
    store = GraphStore(str(tmp_path / "graph.db"))
    store.add_node(
        "prog:HELLO",
        "HELLO",
        "CobolProgram",
        file_path=str(tmp_path / "HELLO.cob"),
        metadata={"source_text": "IDENTIFICATION DIVISION.\nPROGRAM-ID. HELLO.\nDISPLAY 'HELLO'."},
    )
    store.add_node(
        "para:HELLO:MAIN",
        "MAIN",
        "CobolParagraph",
        metadata={"source_text": "DISPLAY 'HELLO'."},
    )
    store.add_node(
        "data:HELLO:AMOUNT",
        "AMOUNT",
        "CobolDataItem",
        metadata={"pic": "9(5)V99", "source_text": "05 AMOUNT PIC 9(5)V99."},
    )
    store.add_node("prog:BYE", "BYE", "CobolProgram", metadata={"source_text": "PROGRAM-ID. BYE."})
    store.add_edge("prog:HELLO", "para:HELLO:MAIN", "perform")
    store.add_edge("prog:HELLO", "data:HELLO:AMOUNT", "moves_to")
    store.add_edge("prog:HELLO", "prog:BYE", "call")
    store.commit()
    return store


def mark_enriched(store: GraphStore) -> None:
    for node in list(store.iter_all_nodes()):
        meta = dict(node.metadata or {})
        meta.setdefault("signature_summary", f"{node.name} signature")
        meta.setdefault("logic_summary", f"{node.name} logic")
        store.sqlite_connection().execute(
            "UPDATE nodes SET metadata = ? WHERE id = ?",
            (json.dumps(meta, sort_keys=True), node.id),
        )
    store.commit()
