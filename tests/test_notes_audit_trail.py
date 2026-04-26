"""NOTES.md audit trail for Phase 3d quality and Integration #15."""

from __future__ import annotations

from pathlib import Path

import pytest

_REPO = Path(__file__).resolve().parents[1]
_NOTES = _REPO / "NOTES.md"


@pytest.mark.skipif(not _NOTES.is_file(), reason="NOTES.md")
def test_notes_has_historical_quality_formulas_section() -> None:
    t = _NOTES.read_text(encoding="utf-8")
    assert "## Historical Quality Formulas" in t
    assert "### Formula v1" in t
    assert "### Formula v2" in t
    assert "0.7266" in t and "0.6524" in t
    assert "Phase 14a baseline" in t and "0.6831" in t and "0.6461" in t
    assert "function_count" in t and "line_density" in t


@pytest.mark.skipif(not _NOTES.is_file(), reason="NOTES.md")
def test_notes_has_integration_15_roadmap_section() -> None:
    t = _NOTES.read_text(encoding="utf-8")
    assert "Integration #15" in t
    assert "RPG" in t
    assert "PL/I" in t
    assert "JCL" in t
    assert "VB6" in t
