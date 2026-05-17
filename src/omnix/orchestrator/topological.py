"""Topological sort with Tarjan SCC batching for the orchestrator.

The orchestrator walks the dependency graph in reverse-dependency order:
dependencies before dependents, so that when a node is dispatched its
rebuilt dependencies are already available.

Edges are given as (dependent, dependency) — the natural shape coming out of
SemanticNode.dependency_edges. The returned order places dependencies first.

Cycles (mutual recursion) become SCCs. The orchestrator batches a whole SCC
into one LLM call rather than trying to break the cycle artificially.

Implementation notes:
  - Tarjan's SCC is written iteratively (explicit stack) to dodge Python's
    recursion-limit ceiling on real Java codebases (10k+ methods).
  - Edge condensation builds a DAG over SCC ids and Kahn's algorithm
    produces the final order.
"""

from __future__ import annotations

from collections import defaultdict, deque
from typing import Hashable, Iterable, TypeVar

NodeId = TypeVar("NodeId", bound=Hashable)


def topo_sort(
    nodes: Iterable[NodeId],
    edges: Iterable[tuple[NodeId, NodeId]],
) -> list[NodeId | list[NodeId]]:
    """Sort `nodes` so dependencies come before dependents.

    Args:
        nodes: every node id in the graph (singletons included).
        edges: (dependent, dependency) pairs.

    Returns:
        A list where each element is either:
          - a single NodeId (size-1 SCC, the common case), or
          - a list[NodeId] (SCC of size > 1, must be dispatched together).

    Raises:
        ValueError: if `edges` references a node id not present in `nodes`.
    """
    node_list: list[NodeId] = list(nodes)
    node_set: set[NodeId] = set(node_list)
    edge_list: list[tuple[NodeId, NodeId]] = list(edges)

    for dep_from, dep_to in edge_list:
        if dep_from not in node_set:
            raise ValueError(f"edge references unknown node: {dep_from!r}")
        if dep_to not in node_set:
            raise ValueError(f"edge references unknown node: {dep_to!r}")

    if not node_list:
        return []

    # adjacency: forward edges as given (dependent -> dependency).
    forward: dict[NodeId, list[NodeId]] = defaultdict(list)
    for src, dst in edge_list:
        forward[src].append(dst)

    sccs = _tarjan_scc(node_list, forward)

    # Map each node to its SCC index.
    node_to_scc: dict[NodeId, int] = {}
    for scc_idx, scc in enumerate(sccs):
        for n in scc:
            node_to_scc[n] = scc_idx

    # Condensation DAG: edge (u_scc -> v_scc) iff u in u_scc, v in v_scc, u!=v_scc.
    # We want dependencies first in output, and our edges are dep -> dependency.
    # In the condensation, an edge from scc(u) to scc(v) means scc(u) DEPENDS ON scc(v),
    # so scc(v) must be emitted first. Kahn's needs in-degree of "things waiting on me",
    # so we invert: build edges scc(v) -> scc(u) (v is a dependency, u depends on it).
    cond_out: dict[int, set[int]] = defaultdict(set)
    cond_in_degree: dict[int, int] = {i: 0 for i in range(len(sccs))}
    for src, dst in edge_list:
        s_idx = node_to_scc[src]
        d_idx = node_to_scc[dst]
        if s_idx == d_idx:
            continue  # intra-SCC edge — not part of condensation
        # dependency direction in condensation: d_idx -> s_idx
        if s_idx not in cond_out[d_idx]:
            cond_out[d_idx].add(s_idx)
            cond_in_degree[s_idx] += 1

    # Kahn's algorithm on the condensation.
    queue: deque[int] = deque(i for i in range(len(sccs)) if cond_in_degree[i] == 0)
    emitted: list[int] = []
    while queue:
        i = queue.popleft()
        emitted.append(i)
        for j in cond_out.get(i, ()):
            cond_in_degree[j] -= 1
            if cond_in_degree[j] == 0:
                queue.append(j)

    if len(emitted) != len(sccs):
        # Should be impossible — condensation is always a DAG.
        raise RuntimeError("condensation graph is not a DAG (internal error)")

    # Materialize each emitted SCC into the public return shape.
    out: list[NodeId | list[NodeId]] = []
    for scc_idx in emitted:
        members = sccs[scc_idx]
        if len(members) == 1:
            out.append(members[0])
        else:
            out.append(list(members))
    return out


def _tarjan_scc(
    nodes: list[NodeId],
    forward: dict[NodeId, list[NodeId]],
) -> list[list[NodeId]]:
    """Iterative Tarjan SCC.

    Returns SCCs in reverse-topological order of the condensation
    (a Tarjan property). We do not rely on that ordering here — Kahn's is
    re-run on the condensation — but the property is documented for clarity.

    Each SCC is a list[NodeId]; size-1 SCCs of nodes WITHOUT a self-loop are
    still returned (so every input node appears in exactly one SCC).
    """
    index_counter = [0]
    stack: list[NodeId] = []
    on_stack: set[NodeId] = set()
    indices: dict[NodeId, int] = {}
    lowlinks: dict[NodeId, int] = {}
    sccs: list[list[NodeId]] = []

    # Iterative DFS state: (node, iterator over neighbors, in-progress flag).
    for start in nodes:
        if start in indices:
            continue

        # Iterative emulation of Tarjan's recursive strongconnect.
        call_stack: list[tuple[NodeId, list[NodeId], int]] = []
        # Initialize start
        indices[start] = index_counter[0]
        lowlinks[start] = index_counter[0]
        index_counter[0] += 1
        stack.append(start)
        on_stack.add(start)
        call_stack.append((start, forward.get(start, []), 0))

        while call_stack:
            v, neighbors, i = call_stack[-1]
            if i < len(neighbors):
                w = neighbors[i]
                call_stack[-1] = (v, neighbors, i + 1)
                if w not in indices:
                    indices[w] = index_counter[0]
                    lowlinks[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack.add(w)
                    call_stack.append((w, forward.get(w, []), 0))
                elif w in on_stack:
                    if indices[w] < lowlinks[v]:
                        lowlinks[v] = indices[w]
            else:
                # All neighbors processed — propagate lowlink to parent and
                # close the SCC if v is a root.
                if lowlinks[v] == indices[v]:
                    component: list[NodeId] = []
                    while True:
                        w = stack.pop()
                        on_stack.discard(w)
                        component.append(w)
                        if w == v:
                            break
                    sccs.append(component)
                call_stack.pop()
                if call_stack:
                    parent_v, _, _ = call_stack[-1]
                    if lowlinks[v] < lowlinks[parent_v]:
                        lowlinks[parent_v] = lowlinks[v]

    return sccs
