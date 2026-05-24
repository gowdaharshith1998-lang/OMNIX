"""Adapter — bridges `omnix.graph.store.GraphStore` to the dispatcher's `_GraphLike`.

The dispatcher is written against a slim Protocol that only asks for
`get_all_nodes() -> Iterable[SemanticNode]`, `get_dependency_edges() -> Iterable[tuple[str,str]]`,
and `get_node(fqn) -> SemanticNode`. The real `GraphStore` exposes `NodeRow` /
`EdgeRow` instead. This adapter does the format translation.

Storage convention (this adapter's contract with `populate_from_semantic_nodes`):
- `NodeRow.id` holds a stable graph FQN. For overloaded Java methods this is
  the semantic FQN plus resolved parameter types, so overloads do not collide.
- `NodeRow.name` holds the unqualified symbol name.
- `NodeRow.type` holds the `SemanticNode.kind` value (v1: "method").
- `NodeRow.metadata` is a JSON dict with keys: `signature`, `resolved_param_types`,
  `resolved_return_type`, and `semantic_fqn`. Round-trips lossless because we
  control both sides.
- `EdgeRow.relationship == "calls"` for dependency edges that the dispatcher cares
  about. Other relationships are ignored by the adapter — orchestrator topo only
  walks call edges.
"""

from __future__ import annotations

import hashlib
from collections import Counter
from typing import Iterable

from omnix.graph.store import GraphStore
from omnix.semantic.node import SemanticNode, SourceLocation


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
        matches = [
            n
            for n in self.get_all_nodes()
            if n.fqn.split("(", 1)[0] == fqn
        ]
        if matches:
            return sorted(matches, key=lambda n: n.fqn)[0]
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
    node_list = list(nodes)
    node_ids = _node_ids_by_identity(node_list)
    graph_ids = set(node_ids.values())
    semantic_to_graph = _semantic_to_graph_id(node_list, node_ids)
    for n in node_list:
        graph_id = node_ids[id(n)]
        # Unqualified name = last dotted segment.
        name = n.fqn.rsplit(".", 1)[-1]
        metadata = {
            "semantic_fqn": n.fqn,
            "signature": n.signature,
            "resolved_param_types": list(n.resolved_param_types),
            "resolved_return_type": n.resolved_return_type,
            "visibility": _visibility_from_signature(n.signature),
            "deprecated": False,
        }
        store.add_node(
            id=graph_id,
            name=name,
            type=n.kind,
            file_path=n.source_location.file_path,
            start_line=n.source_location.line,
            metadata=metadata,
        )
    for n in node_list:
        source_id = node_ids[id(n)]
        for edge in n.dependency_edges:
            target_id = semantic_to_graph.get(edge.target_fqn, edge.target_fqn)
            if drop_external_edges and target_id not in graph_ids:
                continue
            store.add_edge(
                source_id=source_id,
                target_id=target_id,
                relationship=edge.kind,
                metadata={"line": edge.line},
            )
    # GraphStore uses DEFERRED isolation: writes stay in an open transaction
    # until an explicit commit. Without this, close() rolls back our inserts and
    # the next connection sees an empty DB.
    store.commit()


def _node_ids_by_identity(nodes: list[SemanticNode]) -> dict[int, str]:
    fqn_counts = Counter(n.fqn for n in nodes)
    used: set[str] = set()
    out: dict[int, str] = {}
    for n in nodes:
        if fqn_counts[n.fqn] == 1:
            candidate = n.fqn
        else:
            params = ",".join(n.resolved_param_types)
            candidate = f"{n.fqn}({params})"
        if candidate in used:
            sig_hash = hashlib.sha256(n.signature.encode("utf-8")).hexdigest()[:12]
            candidate = f"{candidate}#{sig_hash}"
        suffix = 2
        base_candidate = candidate
        while candidate in used:
            candidate = f"{base_candidate}-{suffix}"
            suffix += 1
        used.add(candidate)
        out[id(n)] = candidate
    return out


def _semantic_to_graph_id(
    nodes: list[SemanticNode], node_ids: dict[int, str]
) -> dict[str, str]:
    grouped: dict[str, list[str]] = {}
    for n in nodes:
        grouped.setdefault(n.fqn, []).append(node_ids[id(n)])
    return {
        semantic_fqn: ids[0]
        for semantic_fqn, ids in grouped.items()
        if len(ids) == 1
    }


def _visibility_from_signature(signature: str) -> str:
    first = (signature.strip().split(" ", 1)[0] if signature.strip() else "").lower()
    if first in {"public", "protected", "private"}:
        return first
    return "package"
