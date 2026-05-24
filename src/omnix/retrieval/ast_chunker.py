"""AST-aware COBOL chunking with explicit line fallback."""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any

_COBOL_LANG: Any = None

try:  # pragma: no cover - depends on optional local grammar availability
    import tree_sitter  # type: ignore[import-untyped]
    import tree_sitter_cobol  # type: ignore[import-untyped]

    _COBOL_LANG = tree_sitter.Language(tree_sitter_cobol.language())
except Exception:  # pragma: no cover - exercised by fallback tests
    tree_sitter = None  # type: ignore[assignment]


@dataclass(frozen=True)
class CodeChunk:
    text: str
    start_line: int
    end_line: int
    node_kind: str


DEFAULT_MAX_CHUNK_CHARS = 2048
MIN_CHUNK_CHARS = 200


def chunk_mode() -> str:
    mode = os.environ.get("OMNIX_CHUNK_MODE", "line").strip().lower()
    if mode not in {"ast", "line", "auto"}:
        mode = "line"
    return mode


def chunk_cobol(source: str, max_chars: int = DEFAULT_MAX_CHUNK_CHARS) -> list[CodeChunk]:
    mode = chunk_mode()
    if mode == "line":
        return _chunk_by_lines(source, max_chars)
    if _COBOL_LANG is None:
        if mode == "ast":
            raise RuntimeError("tree-sitter COBOL grammar unavailable")
        return _chunk_by_lines(source, max_chars)
    try:
        return _chunk_by_ast(source, max_chars)
    except Exception:
        if mode == "ast":
            raise
        return _chunk_by_lines(source, max_chars)


def _chunk_by_ast(source: str, max_chars: int) -> list[CodeChunk]:
    if tree_sitter is None or _COBOL_LANG is None:
        raise RuntimeError("tree-sitter COBOL grammar unavailable")
    parser = tree_sitter.Parser()
    if hasattr(parser, "set_language"):
        parser.set_language(_COBOL_LANG)
    else:
        parser.language = _COBOL_LANG
    tree = parser.parse(source.encode("utf-8"))
    out: list[CodeChunk] = []
    _greedy_merge_split(tree.root_node, source, max_chars, out)
    return out or _chunk_by_lines(source, max_chars)


def _greedy_merge_split(node: Any, source: str, max_chars: int, acc: list[CodeChunk]) -> None:
    children = list(getattr(node, "children", []) or [node])
    buffer: list[Any] = []
    buffer_chars = 0
    for child in children:
        text = source[child.start_byte : child.end_byte]
        if len(text) > max_chars and getattr(child, "children", None):
            if buffer:
                acc.append(_flush(buffer, source))
                buffer, buffer_chars = [], 0
            _greedy_merge_split(child, source, max_chars, acc)
            continue
        if buffer_chars + len(text) > max_chars and buffer:
            acc.append(_flush(buffer, source))
            buffer, buffer_chars = [], 0
        buffer.append(child)
        buffer_chars += len(text)
    if buffer:
        acc.append(_flush(buffer, source))


def _flush(buffer: list[Any], source: str) -> CodeChunk:
    start_byte = buffer[0].start_byte
    end_byte = buffer[-1].end_byte
    text = source[start_byte:end_byte]
    start_line = buffer[0].start_point[0] + 1
    end_line = buffer[-1].end_point[0] + 1
    kinds = sorted({node.type for node in buffer if getattr(node, "type", None)})
    node_kind = "+".join(kinds[:3]) or "node"
    return CodeChunk(text=text, start_line=start_line, end_line=end_line, node_kind=node_kind)


def _chunk_by_lines(source: str, max_chars: int) -> list[CodeChunk]:
    lines = source.splitlines(keepends=True)
    chunks: list[CodeChunk] = []
    buf: list[str] = []
    buf_chars = 0
    start = 1
    for line_no, line in enumerate(lines, start=1):
        if buf_chars + len(line) > max_chars and buf:
            chunks.append(
                CodeChunk(
                    text="".join(buf),
                    start_line=start,
                    end_line=line_no - 1,
                    node_kind="line_fallback",
                )
            )
            buf, buf_chars, start = [], 0, line_no
        buf.append(line)
        buf_chars += len(line)
    if buf:
        chunks.append(
            CodeChunk(
                text="".join(buf),
                start_line=start,
                end_line=len(lines),
                node_kind="line_fallback",
            )
        )
    if not chunks and source:
        chunks.append(CodeChunk(text=source, start_line=1, end_line=1, node_kind="line_fallback"))
    return chunks
