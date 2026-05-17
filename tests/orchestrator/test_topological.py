"""Tests for omnix.orchestrator.topological.topo_sort.

Coverage goals:
  - Trivial cases (empty / singleton / linear chain).
  - Multiple independent chains (Kahn's tie-break tolerant).
  - Diamond (single source, single sink, two parallel paths).
  - Cycles: 1-cycle self-loop, 2-cycle, 3-cycle.
  - Mixed: chain + cycle elsewhere.
  - Error: edge referencing unknown node.
"""

from __future__ import annotations

import pytest

from omnix.orchestrator.topological import topo_sort


def _dependencies_before_dependents(
    order: list[object], edges: list[tuple[object, object]]
) -> bool:
    """Helper: for every (dependent, dependency) edge, dependency must appear
    earlier in `order`. SCCs are treated as a single position.
    """
    position: dict[object, int] = {}
    for idx, entry in enumerate(order):
        if isinstance(entry, list):
            for n in entry:
                position[n] = idx
        else:
            position[entry] = idx
    for dependent, dependency in edges:
        if position[dependency] > position[dependent]:
            return False
    return True


def test_empty_graph_returns_empty_list() -> None:
    assert topo_sort([], []) == []


def test_single_node_no_edges() -> None:
    assert topo_sort(["A"], []) == ["A"]


def test_linear_chain_orders_deps_first() -> None:
    # A depends on B, B depends on C — so C must come first.
    order = topo_sort(["A", "B", "C"], [("A", "B"), ("B", "C")])
    assert order == ["C", "B", "A"]


def test_two_independent_chains_each_ordered() -> None:
    # A->B and C->D. Both chains must have dep before dependent.
    edges: list[tuple[object, object]] = [("A", "B"), ("C", "D")]
    order = topo_sort(["A", "B", "C", "D"], edges)
    assert len(order) == 4
    assert _dependencies_before_dependents(order, edges)


def test_diamond_topology() -> None:
    # A->B, A->C, B->D, C->D. D must precede B and C, both precede A.
    edges: list[tuple[object, object]] = [
        ("A", "B"),
        ("A", "C"),
        ("B", "D"),
        ("C", "D"),
    ]
    order = topo_sort(["A", "B", "C", "D"], edges)
    assert len(order) == 4
    assert _dependencies_before_dependents(order, edges)
    # D first, A last regardless of B/C order.
    assert order[0] == "D"
    assert order[-1] == "A"


def test_self_loop_returned_as_singleton() -> None:
    # Size-1 SCC (a self-loop) unwraps to a bare NodeId per spec.
    order = topo_sort(["A"], [("A", "A")])
    assert order == ["A"]


def test_two_cycle_returned_as_scc() -> None:
    # A <-> B forms a 2-cycle; emitted as a list of the two members.
    order = topo_sort(["A", "B"], [("A", "B"), ("B", "A")])
    assert len(order) == 1
    entry = order[0]
    assert isinstance(entry, list)
    assert set(entry) == {"A", "B"}


def test_three_cycle_returned_as_scc() -> None:
    # A -> B -> C -> A.
    order = topo_sort(["A", "B", "C"], [("A", "B"), ("B", "C"), ("C", "A")])
    assert len(order) == 1
    entry = order[0]
    assert isinstance(entry, list)
    assert set(entry) == {"A", "B", "C"}


def test_mixed_chain_and_cycle() -> None:
    # Linear chain X -> Y; separate 2-cycle A <-> B.
    nodes = ["X", "Y", "A", "B"]
    edges: list[tuple[object, object]] = [
        ("X", "Y"),
        ("A", "B"),
        ("B", "A"),
    ]
    order = topo_sort(nodes, edges)
    # 3 entries: Y (singleton), X (singleton), [A,B] in some order.
    assert len(order) == 3
    flat: list[object] = []
    has_scc = False
    for entry in order:
        if isinstance(entry, list):
            assert set(entry) == {"A", "B"}
            has_scc = True
            flat.extend(entry)
        else:
            flat.append(entry)
    assert has_scc
    assert set(flat) == {"X", "Y", "A", "B"}
    assert _dependencies_before_dependents(order, edges)


def test_edge_references_unknown_node_raises() -> None:
    with pytest.raises(ValueError, match="edge references unknown node"):
        topo_sort(["A"], [("A", "ghost")])


def test_edge_with_unknown_source_raises() -> None:
    with pytest.raises(ValueError, match="edge references unknown node"):
        topo_sort(["A"], [("ghost", "A")])


def test_disconnected_singletons_all_emitted() -> None:
    # No edges — every node appears once as a singleton.
    order = topo_sort(["A", "B", "C", "D"], [])
    assert set(order) == {"A", "B", "C", "D"}
    assert all(not isinstance(e, list) for e in order)


def test_large_chain_does_not_recurse() -> None:
    # 2000-node chain — Tarjan implementation must be iterative.
    n = 2000
    nodes = [f"n{i}" for i in range(n)]
    edges = [(f"n{i}", f"n{i + 1}") for i in range(n - 1)]
    order = topo_sort(nodes, edges)
    assert len(order) == n
    # Last dep must be first emitted.
    assert order[0] == f"n{n - 1}"
    assert order[-1] == "n0"
