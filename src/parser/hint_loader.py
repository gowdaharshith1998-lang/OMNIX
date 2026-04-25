"""Load per-language JSON hints and merge with generic node-type sets."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

_H_DIR = Path(__file__).resolve().parent / "hints"

# Grammar-agnostic defaults (Layer 1)
GENERIC_FUNCTION_NODES: frozenset[str] = frozenset(
    {
        "function_definition",
        "function_declaration",
        "method_definition",
        "method_declaration",
        "function_item",
        "function",
        "func_declaration",
        "subroutine_declaration",
        "constructor_declaration",
        "lambda",
        "arrow_function",
    }
)

GENERIC_CLASS_NODES: frozenset[str] = frozenset(
    {
        "class_definition",
        "class_declaration",
        "struct_definition",
        "struct_declaration",
        "interface_declaration",
        "trait_definition",
        "impl_item",
        "enum_declaration",
        "type_alias_declaration",
    }
)

GENERIC_CALL_NODES: frozenset[str] = frozenset(
    {
        "call_expression",
        "function_call",
        "call",
        "method_invocation",
        "method_call_expression",
        "macro_invocation",
    }
)

GENERIC_IMPORT_NODES: frozenset[str] = frozenset(
    {
        "import_statement",
        "import_declaration",
        "use_declaration",
        "package_clause",
        "include_directive",
        "require_directive",
    }
)


@dataclass
class MergedHints:
    """Generic sets merged with a hint file (or generic-only)."""

    parse_mode: str
    all_function_node_types: frozenset[str]
    all_class_node_types: frozenset[str]
    all_call_node_types: frozenset[str]
    all_import_node_types: frozenset[str]
    hint: dict[str, object] = field(default_factory=dict)


def _read_hint_file(lang: str) -> dict[str, object] | None:
    p = _H_DIR / f"{lang}.json"
    if not p.is_file():
        return None
    try:
        o = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None
    return o if isinstance(o, dict) else None


def load_merged_hints(lang: str, *, parse_mode: str) -> MergedHints:
    """
    *parse_mode* ``\"hinted\"`` merges ``hints/<lang>.json`` when present;
    ``\"generic\"`` uses only built-in node sets.
    """
    fset = set(GENERIC_FUNCTION_NODES)
    cset = set(GENERIC_CLASS_NODES)
    ccall = set(GENERIC_CALL_NODES)
    cimp = set(GENERIC_IMPORT_NODES)
    raw: dict[str, object] = {}
    if parse_mode == "hinted" or parse_mode == "generic":
        data = _read_hint_file(lang) if parse_mode == "hinted" else None
        if data:
            for k, v in data.items():
                raw[k] = v
            for k in data.get("extra_function_nodes", []) or []:
                if isinstance(k, str):
                    fset.add(k)
            for k in data.get("extra_class_nodes", []) or []:
                if isinstance(k, str):
                    cset.add(k)
            for k in data.get("extra_call_nodes", []) or []:
                if isinstance(k, str):
                    ccall.add(k)
            for k in data.get("extra_import_nodes", []) or []:
                if isinstance(k, str):
                    cimp.add(k)
    has_hint = bool(raw) and parse_mode == "hinted"
    modename = "hinted" if has_hint else "generic"
    return MergedHints(
        parse_mode=modename,
        all_function_node_types=frozenset(fset),
        all_class_node_types=frozenset(cset),
        all_call_node_types=frozenset(ccall),
        all_import_node_types=frozenset(cimp),
        hint=raw,
    )
