from __future__ import annotations

import asyncio

from omnix.evolve.dual_evolve import FailedAttempt, co_refine
from omnix.traversal.budget import TraversalBudget
from tests.cobol.graphrag.helpers import graph


def test_dual_evolve_budget_exhausted_noop(tmp_path) -> None:
    store = graph(tmp_path)
    try:
        result = asyncio.run(
            co_refine(FailedAttempt("HELLO", "fail", "prog:HELLO"), store, lambda **_: "{}", TraversalBudget(tokens_remaining=0))
        )
        assert result.tokens_used == 0
        assert not result.has_new_evidence
    finally:
        store.close()
