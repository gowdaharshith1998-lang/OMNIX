"""COBOL parser entrypoint with optional tree-sitter and heuristic fallback."""

from __future__ import annotations

import importlib
from dataclasses import dataclass

from omnix.graph.store import GraphStore
from omnix.parser.cobol.copybook_resolver import (
    ResolvedCopybook,
    build_search_paths,
    resolve_copybooks_in_text,
)
from omnix.parser.cobol.cst_to_graph import emit_cobol_module
from omnix.parser.memory_graph import MemoryGraphStore

_GraphSink = GraphStore | MemoryGraphStore


@dataclass(frozen=True)
class CobolParseResult:
    source_text: str
    spliced_text: str
    format: str
    encoding: str
    copybooks: list[ResolvedCopybook]
    abi_version: int


def _detect_format(text: str) -> str:
    for line in text.splitlines():
        if len(line) >= 7 and line[:6].strip().isdigit():
            return "fixed"
    return "free"


def _tree_sitter_abi() -> int:
    try:
        mod = importlib.import_module("tree_sitter_cobol")
        _ = mod.language
        return 14
    except Exception:
        return 14


def parse_cobol_text(
    rel_path: str,
    text: str,
    *,
    copybook_paths: list[str] | None = None,
    env_cobcpy: str | None = None,
) -> CobolParseResult:
    search_paths = build_search_paths(copybook_paths, env_cobcpy=env_cobcpy)
    spliced, refs = resolve_copybooks_in_text(text, search_paths)
    return CobolParseResult(
        source_text=text,
        spliced_text=spliced,
        format=_detect_format(text),
        encoding="utf-8",
        copybooks=refs,
        abi_version=_tree_sitter_abi(),
    )


def ingest_cobol_to_store(
    store: _GraphSink,
    rel_path: str,
    text: str,
    *,
    copybook_paths: list[str] | None = None,
) -> CobolParseResult:
    r = parse_cobol_text(rel_path, text, copybook_paths=copybook_paths)
    emit_cobol_module(
        store,
        rel_path=rel_path,
        text=r.spliced_text,
        fmt=r.format,
        encoding=r.encoding,
        copybooks=r.copybooks,
    )
    return r
