"""Phase 3b: each modern JSON profile loads and validates."""

from __future__ import annotations

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
