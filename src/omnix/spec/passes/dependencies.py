"""Pass 4: Dependencies — convert SemanticNode.dependency_edges -> DependencyRef.

For each outgoing edge we record:

- `legacy_signature`: the original-codebase signature, fetched from the graph
  via the duck-typed `graph_db.get_legacy_signature(fqn) -> str`. Missing legacy
  is treated as a known v1 data gap and falls back to `""` rather than raising
  — the spec generator should not crash on partial indexes.
- `rebuilt_signature`: the post-modernization signature for the target, via
  `graph_db.get_rebuilt_signature(fqn) -> str | None`. `None` means "target has
  not been rebuilt yet" and the LLM should bind against the legacy signature.

The graph_db parameter is intentionally duck-typed. The orchestrator passes in
the real GraphStore; tests pass a stub. Either way we only touch the two
documented methods.
"""

from __future__ import annotations

from typing import Any, Protocol

from omnix.semantic import SemanticNode
from omnix.spec import DependencyRef


class _GraphDBProtocol(Protocol):  # documentation-only, not enforced
    def get_rebuilt_signature(self, fqn: str) -> str | None: ...
    def get_legacy_signature(self, fqn: str) -> str: ...


def _safe_legacy(graph_db: Any, fqn: str) -> str:
    """Fetch legacy signature, tolerating missing methods or missing entries."""
    getter = getattr(graph_db, "get_legacy_signature", None)
    if getter is None:
        return ""
    try:
        result = getter(fqn)
    except KeyError:
        return ""
    return result if isinstance(result, str) else ""


def _safe_rebuilt(graph_db: Any, fqn: str) -> str | None:
    """Fetch rebuilt signature, returning None if absent or method missing."""
    getter = getattr(graph_db, "get_rebuilt_signature", None)
    if getter is None:
        return None
    try:
        return getter(fqn)
    except KeyError:
        return None


def run(node: SemanticNode, graph_db: Any) -> tuple[DependencyRef, ...]:
    """Build the dependency list for `node` against the current graph state."""
    refs: list[DependencyRef] = []
    for edge in node.dependency_edges:
        legacy = _safe_legacy(graph_db, edge.target_fqn)
        rebuilt = _safe_rebuilt(graph_db, edge.target_fqn)
        refs.append(
            DependencyRef(
                target_fqn=edge.target_fqn,
                kind=edge.kind,
                legacy_signature=legacy,
                rebuilt_signature=rebuilt,
            )
        )
    return tuple(refs)
