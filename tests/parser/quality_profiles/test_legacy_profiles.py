"""Phase 3c: COBOL / HLASM / Fortran custom profile loading and fixture scores."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnix.parser.quality_profiles import load_custom_score, load_profile

_FIX = Path(__file__).resolve().parent / "fixtures"


def _read_fixture(name: str) -> dict:
    p = _FIX / name
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def _score_with_profile(grammar: str, stats: dict) -> float:
    p = load_profile(grammar)
    assert p is not None, f"missing profile for {grammar!r}"
    assert p.formula == "custom_python", grammar
    assert p.python_module, grammar
    fn = load_custom_score(p.python_module)
    return float(fn(stats))


def test_cobol_profile_loads() -> None:
    p = load_profile("cobol")
    assert p is not None
    assert p.grammar == "cobol"
    assert p.formula == "custom_python"


def test_hlasm_profile_loads() -> None:
    p = load_profile("hlasm")
    assert p is not None
    assert p.grammar == "hlasm"
    assert p.formula == "custom_python"


def test_fortran_profile_loads() -> None:
    p = load_profile("fortran")
    assert p is not None
    assert p.grammar == "fortran"
    assert p.formula == "custom_python"


def test_cobol_substantial_scores_above_threshold() -> None:
    s = _score_with_profile("cobol", _read_fixture("cobol_substantial_stats.json"))
    assert s >= 0.7


def test_cobol_stub_scores_low() -> None:
    s = _score_with_profile("cobol", _read_fixture("cobol_stub_stats.json"))
    assert s < 0.3


def test_hlasm_substantial_scores_above_threshold() -> None:
    s = _score_with_profile("hlasm", _read_fixture("hlasm_substantial_stats.json"))
    assert s >= 0.7


def test_fortran_substantial_scores_above_threshold() -> None:
    s = _score_with_profile("fortran", _read_fixture("fortran_substantial_stats.json"))
    assert s >= 0.7


def test_legacy_profiles_load_without_grammar_packages() -> None:
    # Profile load must not import tree_sitter / grammar wheels (parse-time concern).
    for g in ("cobol", "hlasm", "fortran"):
        p = load_profile(g)
        assert p is not None, g
        assert callable(load_custom_score(p.python_module))
