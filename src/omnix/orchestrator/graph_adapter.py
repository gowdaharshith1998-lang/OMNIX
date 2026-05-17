"""Adapter — bridges `omnix.graph.store.GraphStore` to the dispatcher's `_GraphLike`.

The dispatcher is written against a slim Protocol that only asks for
`get_all_nodes() -> Iterable[SemanticNode]`, `get_dependency_edges() -> Iterable[tuple[str,str]]`,
and `get_node(fqn) -> SemanticNode`. The real `GraphStore` exposes `NodeRow` /
`EdgeRow` instead. This adapter does the format translation.

Storage convention (this adapter's contract with `populate_from_semantic_nodes`):
- `NodeRow.id` holds the FQN (used as primary key).
- `NodeRow.name` holds the unqualified symbol name.
- `NodeRow.type` holds the `SemanticNode.kind` value (v1: "method").
- `NodeRow.metadata` is a JSON dict with keys: `signature`, `resolved_param_types`,
  `resolved_return_type`. Round-trips lossless because we control both sides.
- `EdgeRow.relationship == "calls"` for dependency edges that the dispatcher cares
  about. Other relationships are ignored by the adapter — orchestrator topo only
  walks call edges.
"""

from __future__ import annotations

import json
from typing import Iterable

from omnix.graph.store import GraphStore
from omnix.semantic.node import DependencyEdge, SemanticNode, SourceLocation


class GraphStoreAdapter:
    """Read-side adapter — wraps a GraphStore as `_GraphLike` for the dispatcher."""

    def __init__(self, store: GraphStore) -> None:
        self._store = store

    def get_all_nodes(self) -> list[SemanticNode]:
        nodes: list[SemanticNode] = []
        for nr in self._store.get_all_nodes():
            md = nr.metadata or {}
            nodes.append(
                SemanticNode(
                    fqn=nr.id,
                    kind=nr.type or "method",
                    signature=md.get("signature", ""),
                    resolved_param_types=tuple(md.get("resolved_param_types", [])),
                    resolved_return_type=md.get("resolved_return_type"),
                    # Dependency edges are reconstructed from EdgeRow via
                    # get_dependency_edges(); per-node edge tuples are not
                    # required by the dispatcher's _GraphLike protocol.
                    dependency_edges=(),
                    source_location=SourceLocation(
                        file_path=nr.file_path or "",
                        line=nr.start_line or 0,
                    ),
                )
            )
        return nodes

    def get_dependency_edges(self) -> list[tuple[str, str]]:
        edges: list[tuple[str, str]] = []
        for er in self._store.get_all_edges():
            if er.relationship == "calls":
                edges.append((er.source_id, er.target_id))
        return edges

    def get_node(self, fqn: str) -> SemanticNode:
        for n in self.get_all_nodes():
            if n.fqn == fqn:
                return n
        raise KeyError(fqn)


def populate_from_semantic_nodes(
    store: GraphStore,
    nodes: Iterable[SemanticNode],
    *,
    drop_external_edges: bool = True,
) -> None:
    """Write a list of SemanticNode into GraphStore matching the adapter's convention.

    Args:
        store: target GraphStore (must be writable).
        nodes: SemanticNodes to write — typically the output of `parse_file`.
        drop_external_edges: when True (default), only intra-project dependency
            edges are added — edges pointing at FQNs not in `nodes` (e.g.
            java.lang.String.length) are silently dropped. Matches the
            dispatcher's `_collect_graph_inputs` policy of dropping out-of-graph
            dependencies before topo sort.
    """
    fqns = {n.fqn for n in nodes}
    for n in nodes:
        # Unqualified name = last dotted segment.
        name = n.fqn.rsplit(".", 1)[-1]
        metadata = {
            "signature": n.signature,
            "resolved_param_types": list(n.resolved_param_types),
            "resolved_return_type": n.resolved_return_type,
        }
        store.add_node(
            id=n.fqn,
            name=name,
            type=n.kind,
            file_path=n.source_location.file_path,
            start_line=n.source_location.line,
            metadata=metadata,
        )
    for n in nodes:
        for edge in n.dependency_edges:
            if drop_external_edges and edge.target_fqn not in fqns:
                continue
            store.add_edge(
                source_id=n.fqn,
                target_id=edge.target_fqn,
                relationship=edge.kind,
                metadata={"line": edge.line},
            )
    # GraphStore uses DEFERRED isolation: writes stay in an open transaction
    # until an explicit commit. Without this, close() rolls back our inserts and
    # the next connection sees an empty DB.
    store.commit()
