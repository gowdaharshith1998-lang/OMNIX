"""Map file extensions to Tree-sitter grammar packages (optional imports)."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path

from tree_sitter import Language

# (grammar_name, is_tsx) — TypeScript/TSX parser handles JS/TS/TSX/JSX.
# Pip package names verified against PyPI / importlib module names (omit if uncertain).
SUGGESTED_INSTALL: dict[str, str] = {
    "python": "pip install tree-sitter-python",
    "typescript": "pip install tree-sitter-typescript",
    "c": "pip install tree-sitter-c",
    "cpp": "pip install tree-sitter-cpp",
    "csharp": "pip install tree-sitter-c-sharp",
    "go": "pip install tree-sitter-go",
    "rust": "pip install tree-sitter-rust",
    "java": "pip install tree-sitter-java",
    "kotlin": "pip install tree-sitter-kotlin",
    "swift": "pip install tree-sitter-swift",
    "scala": "pip install tree-sitter-scala",
    "ruby": "pip install tree-sitter-ruby",
    "php": "pip install tree-sitter-php",
    "lua": "pip install tree-sitter-lua",
    "bash": "pip install tree-sitter-bash",
    "sql": "pip install tree-sitter-sql",
    "zig": "pip install tree-sitter-zig",
    "cobol": "pip install tree-sitter-cobol",
}


_GRAMMAR_BY_EXT: dict[str, tuple[str, bool]] = {
    ".py": ("python", False),
    ".pyi": ("python", False),
    ".pyw": ("python", False),
    ".pyx": ("python", False),
    ".ts": ("typescript", False),
    ".tsx": ("typescript", True),
    ".js": ("typescript", False),
    ".jsx": ("typescript", True),
    ".mjs": ("typescript", False),
    ".c": ("c", False),
    ".h": ("c", False),
    ".cc": ("cpp", False),
    ".cpp": ("cpp", False),
    ".cxx": ("cpp", False),
    ".hpp": ("cpp", False),
    ".cs": ("csharp", False),
    ".go": ("go", False),
    ".rs": ("rust", False),
    ".java": ("java", False),
    ".kt": ("kotlin", False),
    ".kts": ("kotlin", False),
    ".swift": ("swift", False),
    ".scala": ("scala", False),
    ".rb": ("ruby", False),
    ".php": ("php", False),
    ".lua": ("lua", False),
    ".sh": ("bash", False),
    ".bash": ("bash", False),
    ".sql": ("sql", False),
    ".cob": ("cobol", False),
    ".cbl": ("cobol", False),
    ".zig": ("zig", False),
}


@dataclass(frozen=True)
class DetectResult:
    """Result of grammar resolution for a path."""

    grammar_name: str
    """Canonical grammar key, e.g. ``python`` or empty if unknown ext."""

    inferred_lang: str
    """Same as grammar when known, else empty."""

    language: Language | None
    """``None`` if skipped or not installed."""

    is_tsx: bool
    """For TypeScript grammar: use TSX-style parser (TSX/JSX)."""

    skip_reason: str | None
    """``unknown_extension``, ``no_grammar``, or ``None`` when OK."""


def try_load_typescript(*, is_tsx: bool) -> Language | None:
    try:
        mod = importlib.import_module("tree_sitter_typescript")
    except ImportError:
        return None
    if is_tsx:
        return Language(mod.language_tsx())  # type: ignore[union-attr]
    return Language(mod.language_typescript())  # type: ignore[union-attr]


def try_load_language_for_grammar(grammar: str) -> Language | None:
    """Load ``Language`` for a grammar, or None if the wheel is not installed."""
    if grammar == "typescript":  # pragma: no cover
        return try_load_typescript(is_tsx=False)
    modmap = {
        "python": "tree_sitter_python",
        "c": "tree_sitter_c",
        "cpp": "tree_sitter_cpp",
        "csharp": "tree_sitter_c_sharp",
        "go": "tree_sitter_go",
        "rust": "tree_sitter_rust",
        "java": "tree_sitter_java",
        "kotlin": "tree_sitter_kotlin",
        "swift": "tree_sitter_swift",
        "scala": "tree_sitter_scala",
        "ruby": "tree_sitter_ruby",
        "php": "tree_sitter_php",
        "lua": "tree_sitter_lua",
        "bash": "tree_sitter_bash",
        "sql": "tree_sitter_sql",
        "cobol": "tree_sitter_cobol",
        "zig": "tree_sitter_zig",
    }
    mname = modmap.get(grammar)
    if mname is None:
        return None
    try:
        mod = importlib.import_module(mname)
    except ImportError:
        return None
    if hasattr(mod, "language"):
        return Language(mod.language())  # type: ignore[no-untyped-call]
    return None


def grammar_for_extension(ext: str) -> str | None:
    """Return canonical grammar name for a file extension (with leading dot), or None."""
    e = ext if ext.startswith(".") else f".{ext}"
    e = e.lower()
    row = _GRAMMAR_BY_EXT.get(e)
    return row[0] if row else None


def detect_for_path(path: Path) -> DetectResult:
    ext = path.suffix.lower()
    row = _GRAMMAR_BY_EXT.get(ext)
    if not row:
        return DetectResult(
            grammar_name="",
            inferred_lang="",
            language=None,
            is_tsx=False,
            skip_reason="unknown_extension",
        )
    g, is_tsx = row
    if g == "typescript":
        lang = try_load_typescript(is_tsx=is_tsx)
    else:
        lang = try_load_language_for_grammar(g)
    if lang is None:
        return DetectResult(
            grammar_name=g,
            inferred_lang=g,
            language=None,
            is_tsx=is_tsx,
            skip_reason="no_grammar",
        )
    return DetectResult(
        grammar_name=g,
        inferred_lang=g,
        language=lang,
        is_tsx=is_tsx,
        skip_reason=None,
    )
