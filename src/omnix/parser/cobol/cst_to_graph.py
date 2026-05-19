"""COBOL CST/heuristic parse to graph nodes/edges."""

from __future__ import annotations

from omnix.graph.store import GraphStore
from omnix.parser.cobol.copybook_resolver import ResolvedCopybook
from omnix.parser.memory_graph import MemoryGraphStore

_GraphSink = GraphStore | MemoryGraphStore


def emit_cobol_module(
    store: _GraphSink,
    *,
    rel_path: str,
    text: str,
    fmt: str,
    encoding: str,
    copybooks: list[ResolvedCopybook],
) -> None:
    lc = text.count("\n") + 1 if text else 1
    file_id = rel_path
    mod_id = f"{rel_path}::CobolModule"
    store.add_node(
        id=file_id,
        name=rel_path.rsplit("/", 1)[-1],
        type="file",
        file_path=rel_path,
        start_line=1,
        end_line=lc,
        complexity=lc,
        metadata={"language": "cobol"},
    )
    store.add_node(
        id=mod_id,
        name=rel_path.rsplit("/", 1)[-1],
        type="CobolModule",
        file_path=rel_path,
        start_line=1,
        end_line=lc,
        complexity=lc,
        metadata={
            "path": rel_path,
            "byte_count": len(text.encode("utf-8", errors="replace")),
            "format": fmt,
            "encoding": encoding,
        },
    )
    store.add_edge(file_id, mod_id, "DEFINES")
    for idx, ref in enumerate(copybooks):
        cb_id = f"{rel_path}::copybook::{idx}::{ref.name}"
        store.add_node(
            id=cb_id,
            name=ref.name,
            type="Copybook",
            file_path=ref.path,
            start_line=1,
            end_line=1,
            complexity=1,
            metadata={"resolved": ref.resolved, "path": ref.path},
        )
        store.add_edge(mod_id, cb_id, "CopybookInclude", metadata={"resolved": ref.resolved})
