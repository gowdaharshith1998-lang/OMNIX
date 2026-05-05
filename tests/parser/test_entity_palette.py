"""Entity-type palette (slice-19) — backend exporter."""

from __future__ import annotations

from src.graph.exporter import FALLBACK_COLOR, _TYPE_COLORS, color_for_type

_EXPECTED_ENTITY_TYPES = frozenset(
    {"code", "people", "decision", "thread", "ticket", "document", "process"}
)


def test_palette_has_seven_types() -> None:
    assert len(_EXPECTED_ENTITY_TYPES) == 7
    for key in _EXPECTED_ENTITY_TYPES:
        assert key in _TYPE_COLORS


def test_palette_hex_values_match_spec() -> None:
    # code: cyan, people: amber, decision: purple, thread: lavender,
    # ticket: orange, document: blue-gray, process: teal-green
    assert _TYPE_COLORS["code"] == "#5eead4"
    assert _TYPE_COLORS["people"] == "#fbbf24"
    assert _TYPE_COLORS["decision"] == "#d8b4fe"
    assert _TYPE_COLORS["thread"] == "#a5b4fc"
    assert _TYPE_COLORS["ticket"] == "#fb923c"
    assert _TYPE_COLORS["document"] == "#5fa3ff"
    assert _TYPE_COLORS["process"] == "#34d399"


def test_palette_unknown_returns_fallback() -> None:
    assert color_for_type("totally_unknown_type_xyz") == FALLBACK_COLOR
    assert FALLBACK_COLOR == "#9ca3af"
