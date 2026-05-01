"""Layer 5 semantic equivalence (R7)."""

from __future__ import annotations

from scan.turboscan.generator_inliner import inlined_int_pair, monadic_reference_pair


def test_R7_semantic_equivalence_for_matched_seeds() -> None:
    for seed in range(500):
        assert inlined_int_pair(seed) == monadic_reference_pair(seed)
