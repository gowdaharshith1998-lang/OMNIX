from __future__ import annotations

from omnix.retrieval.rrf import reciprocal_rank_fusion


def test_hand_computed_rrf_order() -> None:
    fused = reciprocal_rank_fusion([["a", "b"], ["b", "c"]], k=60)
    assert fused[0][0] == "b"
