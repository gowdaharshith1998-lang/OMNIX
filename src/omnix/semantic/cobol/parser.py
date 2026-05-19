"""Heuristic COBOL semantic extraction to graph nodes/edges."""

from __future__ import annotations

import re

from omnix.graph.store import GraphStore
from omnix.parser.memory_graph import MemoryGraphStore

_GraphSink = GraphStore | MemoryGraphStore


def parse_cobol_semantic(store: _GraphSink, rel_path: str, text: str) -> None:
    file_id = rel_path
    prog = rel_path.rsplit("/", 1)[-1].split(".")[0].upper()
    prog_id = f"{rel_path}::CobolProgram::{prog}"
    lc = text.count("\n") + 1 if text else 1
    store.add_node(id=file_id, name=rel_path.rsplit("/", 1)[-1], type="file", file_path=rel_path, start_line=1, end_line=lc, complexity=lc, metadata={"language": "cobol"})
    store.add_node(id=prog_id, name=prog, type="CobolProgram", file_path=rel_path, complexity=lc, metadata={})
    store.add_edge(file_id, prog_id, "DEFINES")

    divisions = []
    for m in re.finditer(r"^\s*([A-Z-]+)\s+DIVISION\.", text, flags=re.IGNORECASE | re.MULTILINE):
        name = m.group(1).upper()
        did = f"{prog_id}::division::{name}"
        store.add_node(id=did, name=name, type="CobolDivision", file_path=rel_path, complexity=1, metadata={})
        store.add_edge(prog_id, did, "DEFINES")
        divisions.append(did)

    for m in re.finditer(r"^\s*([A-Z0-9-]+)\s+SECTION\.", text, flags=re.IGNORECASE | re.MULTILINE):
        name = m.group(1).upper()
        sid = f"{prog_id}::section::{name}"
        store.add_node(id=sid, name=name, type="CobolSection", file_path=rel_path, complexity=1, metadata={})
        anchor = divisions[-1] if divisions else prog_id
        store.add_edge(anchor, sid, "DEFINES")

    para_re = re.compile(r"^\s*([A-Z0-9-]+)\.\s*$", re.IGNORECASE | re.MULTILINE)
    for i, m in enumerate(para_re.finditer(text)):
        name = m.group(1).upper()
        pid = f"{prog_id}::paragraph::{i}::{name}"
        store.add_node(id=pid, name=name, type="CobolParagraph", file_path=rel_path, complexity=1, metadata={})
        store.add_edge(prog_id, pid, "DEFINES")

    data_re = re.compile(r"^\s*(\d{2})\s+([A-Z0-9-]+)\s+PIC\s+([^\.]+)\.", re.IGNORECASE | re.MULTILINE)
    for i, m in enumerate(data_re.finditer(text)):
        level = int(m.group(1))
        name = m.group(2).upper()
        pic = m.group(3).strip().upper()
        did = f"{prog_id}::data::{i}::{name}"
        store.add_node(id=did, name=name, type="CobolDataItem", file_path=rel_path, complexity=1, metadata={"level": level, "pic": pic})
        store.add_edge(prog_id, did, "DEFINES")

    for m in re.finditer(r"\bPERFORM\s+([A-Z0-9-]+)(?:\s+THRU\s+([A-Z0-9-]+))?", text, flags=re.IGNORECASE):
        target = m.group(1).upper()
        thru = m.group(2).upper() if m.group(2) else None
        sid = f"{prog_id}::stmt::perform::{m.start()}"
        store.add_node(id=sid, name="PERFORM", type="CobolStatement", file_path=rel_path, complexity=1, metadata={"thru": thru})
        store.add_edge(prog_id, sid, "DEFINES")
        store.add_edge(sid, f"{prog_id}::paragraph::0::{target}", "perform", metadata={"target": target, "thru": thru})

    for m in re.finditer(r"\bCALL\s+['\"]?([A-Z0-9-]+)['\"]?", text, flags=re.IGNORECASE):
        target = m.group(1).upper()
        sid = f"{prog_id}::stmt::call::{m.start()}"
        store.add_node(id=sid, name="CALL", type="CobolStatement", file_path=rel_path, complexity=1, metadata={})
        store.add_edge(sid, f"CobolProgram::{target}", "call", metadata={"dynamic": "'" not in m.group(0) and '"' not in m.group(0)})

    move_re = re.compile(r"\bMOVE\s+([A-Z0-9-]+)\s+TO\s+([A-Z0-9-]+)", re.IGNORECASE)
    for m in move_re.finditer(text):
        src = m.group(1).upper()
        dst = m.group(2).upper()
        sid = f"{prog_id}::stmt::move::{m.start()}"
        store.add_node(id=sid, name="MOVE", type="CobolStatement", file_path=rel_path, complexity=1, metadata={})
        store.add_edge(sid, prog_id, "moves_to", metadata={"src": src, "dst": dst, "source_pic": None, "target_pic": None})

    for m in re.finditer(r"\b(READ|OPEN INPUT)\s+([A-Z0-9-]+)", text, flags=re.IGNORECASE):
        store.add_edge(prog_id, f"FILE::{m.group(2).upper()}", "reads_file")
    for m in re.finditer(r"\b(WRITE|OPEN OUTPUT)\s+([A-Z0-9-]+)", text, flags=re.IGNORECASE):
        store.add_edge(prog_id, f"FILE::{m.group(2).upper()}", "writes_file")
