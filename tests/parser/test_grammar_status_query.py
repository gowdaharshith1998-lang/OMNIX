"""Unit tests for :mod:`src.parser.grammar_status_query`."""

from __future__ import annotations

from src.parser.grammar_status_query import _sanitize_extension


def test_sanitize_extension_surrogate_yields_hex() -> None:
    raw = "a" + "\ud800" + "z"
    clean, hx = _sanitize_extension(raw)
    assert "\ufffd" in clean or clean != raw
    assert hx is not None
    assert len(hx) >= 4
