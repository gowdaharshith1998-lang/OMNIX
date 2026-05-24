"""Shallow thought-level MCTS for rebuild-approach refinement."""

from __future__ import annotations

import math
import os
from collections.abc import Callable
from dataclasses import dataclass, field


@dataclass
class ThoughtNode:
    thought: str
    parent: "ThoughtNode | None" = None
    children: list["ThoughtNode"] = field(default_factory=list)
    visits: int = 0
    total_reward: float = 0.0

    def ucb1(self, parent_visits: int, c: float = 1.41) -> float:
        if self.visits == 0:
            return float("inf")
        exploit = self.total_reward / self.visits
        explore = c * math.sqrt(math.log(max(parent_visits, 1)) / self.visits)
        return exploit + explore


def mcts_budget() -> int:
    try:
        return max(0, int(os.environ.get("OMNIX_MCTS_BUDGET", "8")))
    except ValueError:
        return 8


def mcts_enabled() -> bool:
    return os.environ.get("OMNIX_MCTS_MODE", "off").strip().lower() in {"on", "auto"}


def search(
    seed_thoughts: list[str],
    expand_fn: Callable[[ThoughtNode], list[str]],
    evaluate_fn: Callable[[ThoughtNode], float],
    budget: int | None = None,
) -> ThoughtNode:
    budget = mcts_budget() if budget is None else max(0, budget)
    root = ThoughtNode(thought="root")
    for seed in seed_thoughts:
        root.children.append(ThoughtNode(thought=seed, parent=root))
    if not root.children or budget == 0:
        return root

    iterations = 0
    while iterations < budget:
        leaf = _select(root)
        if leaf.visits > 0 and not leaf.children:
            for thought in expand_fn(leaf):
                leaf.children.append(ThoughtNode(thought=thought, parent=leaf))
            if leaf.children:
                leaf = leaf.children[0]
        reward = max(0.0, min(1.0, evaluate_fn(leaf)))
        _backprop(leaf, reward)
        iterations += 1
    return _best_leaf(root)


def format_failure_analysis_with_thought(failures: list[dict], thought: str | None) -> str:
    parts: list[str] = []
    if thought:
        parts.append(f"MCTS winning thought: {thought}")
    for failure in failures:
        parts.append(
            "Gate 6 failure "
            f"{failure.get('fixture_id', '<unknown>')}: "
            f"legacy={failure.get('legacy_stdout', '')!r} "
            f"candidate={failure.get('candidate_stdout', '')!r}"
        )
    return "\n".join(parts)


def _select(node: ThoughtNode) -> ThoughtNode:
    while node.children:
        node = max(node.children, key=lambda child: child.ucb1(node.visits))
    return node


def _backprop(node: ThoughtNode, reward: float) -> None:
    current: ThoughtNode | None = node
    while current is not None:
        current.visits += 1
        current.total_reward += reward
        current = current.parent


def _best_leaf(root: ThoughtNode) -> ThoughtNode:
    best: ThoughtNode | None = None
    best_avg = -1.0
    stack = [root]
    while stack:
        node = stack.pop()
        if node.visits > 0 and not node.children:
            avg = node.total_reward / node.visits
            if avg > best_avg:
                best_avg, best = avg, node
        stack.extend(node.children)
    return best if best is not None else root
