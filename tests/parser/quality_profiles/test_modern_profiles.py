"""Phase 3b: each modern JSON profile loads and validates."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.parser.quality_profiles import load_profile


@pytest.mark.parametrize(
    "g",
    (
        "python",
        "typescript",
        "javascript",
        "go",
        "rust",
        "java",
        "generic",
    ),
)
def test_modern_profile_loads_and_validates(g: str) -> None:
    p = load_profile(g)
    assert p is not None, g
    assert p.grammar == g
    assert p.formula == "weighted_sum"
    assert p.profile_version == 1
    assert p.weights
    s = sum(p.weights.values())
    assert s <= 1.01, f"{g} weights sum to {s}"


def test_expected_range_metadata_in_profile_jsons() -> None:
    base = Path(__file__).resolve().parents[3] / "src" / "parser" / "quality_profiles"
    for name in (
        "python",
        "typescript",
        "javascript",
        "go",
        "rust",
        "java",
        "generic",
    ):
        p = base / f"{name}.json"
        data = json.loads(p.read_text(encoding="utf-8"))
        assert data.get("quality_formula_version") == 2, name
        er = data.get("expected_range")
        assert isinstance(er, dict), name
        for k in ("min", "max", "mean", "std", "n_samples", "samples"):
            assert k in er, f"{name} missing {k}"
        assert er["n_samples"] >= 3, name
        assert len(er["samples"]) == er["n_samples"], name
        for s in er["samples"]:
            assert "name" in s and "q" in s and "nodes" in s and "commit_sha" in s, name
