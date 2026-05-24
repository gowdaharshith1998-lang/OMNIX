from __future__ import annotations


def test_mcts_disabled_by_default(monkeypatch) -> None:
    from omnix.traversal.thought_mcts import mcts_enabled

    monkeypatch.delenv("OMNIX_MCTS_MODE", raising=False)

    assert not mcts_enabled()


def test_budget_respected() -> None:
    from omnix.traversal.thought_mcts import ThoughtNode, search

    evaluations = 0

    def expand(_node: ThoughtNode) -> list[str]:
        return ["child"]

    def evaluate(_node: ThoughtNode) -> float:
        nonlocal evaluations
        evaluations += 1
        return 0.5

    search(["seed"], expand, evaluate, budget=3)

    assert evaluations == 3


def test_ucb1_selection_prefers_high_reward_after_visits() -> None:
    from omnix.traversal.thought_mcts import ThoughtNode

    high = ThoughtNode("high", visits=4, total_reward=3.6)
    low = ThoughtNode("low", visits=4, total_reward=0.4)

    assert high.ucb1(parent_visits=8) > low.ucb1(parent_visits=8)


def test_best_leaf_returned_after_search() -> None:
    from omnix.traversal.thought_mcts import ThoughtNode, search

    def expand(node: ThoughtNode) -> list[str]:
        return [f"{node.thought} refined"]

    def evaluate(node: ThoughtNode) -> float:
        return 1.0 if "good" in node.thought else 0.0

    best = search(["bad", "good"], expand, evaluate, budget=4)

    assert "good" in best.thought


def test_zero_visits_node_has_inf_ucb() -> None:
    from omnix.traversal.thought_mcts import ThoughtNode

    assert ThoughtNode("new").ucb1(parent_visits=10) == float("inf")


def test_backprop_updates_ancestors() -> None:
    from omnix.traversal.thought_mcts import ThoughtNode, _backprop

    root = ThoughtNode("root")
    child = ThoughtNode("child", parent=root)

    _backprop(child, 0.75)

    assert child.visits == 1
    assert root.visits == 1
    assert child.total_reward == 0.75
    assert root.total_reward == 0.75


def test_winning_thought_can_route_dual_evolve_parser() -> None:
    from omnix.evolve.dual_evolve import parse_failure_analysis
    from omnix.traversal.thought_mcts import format_failure_analysis_with_thought

    analysis = format_failure_analysis_with_thought(
        [{"fixture_id": "fixture-1", "legacy_stdout": "A   \n", "candidate_stdout": "A\n"}],
        "focus on data-item padding",
    )

    assert "WORKING-STORAGE PIC clause" in parse_failure_analysis(analysis)
