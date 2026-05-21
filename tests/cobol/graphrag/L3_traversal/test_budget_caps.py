from __future__ import annotations

from omnix.traversal.budget import TraversalBudget


def test_budget_exhaustion_returns_false() -> None:
    budget = TraversalBudget(tokens_remaining=1, turns_remaining=1)
    budget.deduct(10)
    assert not budget.can_continue()
