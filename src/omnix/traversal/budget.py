"""Traversal budget caps."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class TraversalBudget:
    tokens_remaining: int = 30000
    turns_remaining: int = 8
    hops_used: int = 0
    max_hops: int = 4
    force_after_extra_hop: bool = False

    def can_continue(self) -> bool:
        return self.tokens_remaining > 0 and self.turns_remaining > 0 and self.hops_used <= self.max_hops

    def deduct(self, tokens: int) -> None:
        self.tokens_remaining = max(0, self.tokens_remaining - max(0, tokens))
        self.turns_remaining = max(0, self.turns_remaining - 1)

    def note_hop(self, count: int = 1) -> None:
        self.hops_used += max(0, count)

    def force_sufficient_after_one_more_hop(self) -> None:
        self.force_after_extra_hop = True
        self.max_hops = max(self.max_hops, self.hops_used + 1)
