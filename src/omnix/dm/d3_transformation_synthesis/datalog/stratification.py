"""Stratification check — reject programs with recursion through negation.

A Datalog program is *stratified* iff its predicate-dependency graph contains
no SCC with a negative edge. We build the graph (with edge sign = positive or
negative), run Tarjan SCC, then check each SCC.
"""

from __future__ import annotations

from typing import Dict, List, Set, Tuple

from .ast import Program


class StratificationError(ValueError):
    """Raised when a program contains recursion through negation."""


def stratify(program: Program) -> Tuple[int, ...]:
    """Return a tuple parallel to ``program.rules`` mapping each rule to its
    stratum index. Raises :class:`StratificationError` if the program is not
    stratified.
    """
    # 1. Build dependency graph with edge sign.
    graph: Dict[str, List[Tuple[str, bool]]] = {}
    for r in program.rules:
        graph.setdefault(r.head.predicate, [])
        for atom in r.body:
            graph[r.head.predicate].append((atom.predicate, atom.negated))
            graph.setdefault(atom.predicate, [])

    # 2. Tarjan SCC over the unsigned graph; check sign within SCCs.
    sccs = _tarjan_scc(graph)
    # For each SCC of size > 1 OR a self-loop, any negative edge inside is bad.
    for scc in sccs:
        members = set(scc)
        if len(scc) == 1:
            self_loop = any(t == scc[0] for (t, _) in graph[scc[0]])
            if not self_loop:
                continue
        for pred in scc:
            for (target, negated) in graph[pred]:
                if target in members and negated:
                    raise StratificationError(
                        f"negation through cycle: {pred!r} → not {target!r}"
                    )

    # 3. Assign strata by topological order of SCCs.
    pred_to_scc: Dict[str, int] = {}
    for i, scc in enumerate(sccs):
        for p in scc:
            pred_to_scc[p] = i
    # SCC graph: edge SCC_a → SCC_b if predicate in a depends on predicate in b.
    scc_edges: Dict[int, Set[int]] = {i: set() for i in range(len(sccs))}
    for src, targets in graph.items():
        a = pred_to_scc[src]
        for (t, _) in targets:
            b = pred_to_scc[t]
            if a != b:
                scc_edges[a].add(b)
    # Stratum number = longest path from any sink upward. Sinks have stratum 0.
    stratum_of: Dict[int, int] = {}

    def _strat(i: int) -> int:
        if i in stratum_of:
            return stratum_of[i]
        deps = scc_edges[i]
        if not deps:
            stratum_of[i] = 0
        else:
            stratum_of[i] = 1 + max(_strat(j) for j in deps)
        return stratum_of[i]

    rule_strata: List[int] = []
    for r in program.rules:
        rule_strata.append(_strat(pred_to_scc[r.head.predicate]))
    return tuple(rule_strata)


def _tarjan_scc(graph: Dict[str, List[Tuple[str, bool]]]) -> List[List[str]]:
    index_counter = [0]
    stack: List[str] = []
    lowlinks: Dict[str, int] = {}
    index: Dict[str, int] = {}
    on_stack: Dict[str, bool] = {}
    result: List[List[str]] = []

    def strongconnect(node: str) -> None:
        index[node] = index_counter[0]
        lowlinks[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack[node] = True
        for (successor, _neg) in graph.get(node, []):
            if successor not in index:
                strongconnect(successor)
                lowlinks[node] = min(lowlinks[node], lowlinks[successor])
            elif on_stack.get(successor, False):
                lowlinks[node] = min(lowlinks[node], index[successor])
        if lowlinks[node] == index[node]:
            component: List[str] = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                component.append(w)
                if w == node:
                    break
            result.append(component)

    for node in list(graph.keys()):
        if node not in index:
            strongconnect(node)
    return result


__all__ = ["StratificationError", "stratify"]
