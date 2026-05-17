"""SemanticNode + DependencyEdge — wire format between semantic layer and downstream.

v1 contract (M1, subject to revision through M2):
- Lean by design: only the 5 tractable spec passes consume these fields.
- frozen=True for hashability + value semantics (receipt-signing relies on this).
- to_json/from_json are deterministic (sorted keys) — required for receipt determinism.

Field rationale:
- fqn: fully-qualified name, dotted (e.g. "org.apache.commons.lang.StringUtils.reverse").
  Used as primary key in GraphStore. NEVER contains spaces or whitespace.
- kind: "method" | "class" | "field". v1 only emits "method" until M2 widens scope.
- signature: canonical form including modifiers + return + param-types.
  Example: "public static String reverse(String)". Deterministic for the same source.
- resolved_param_types: list of FQNs (e.g. ["java.lang.String"]). Empty list for zero-arg.
- resolved_return_type: FQN or None for void.
- dependency_edges: outgoing edges this node creates.
- source_location: where this symbol is defined.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class SourceLocation:
    """Source coordinates for a symbol."""

    file_path: str
    line: int
    column: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SourceLocation:
        return cls(file_path=d["file_path"], line=int(d["line"]), column=int(d.get("column", 0)))


@dataclass(frozen=True)
class DependencyEdge:
    """An outgoing reference from one semantic node to another.

    kind values (v1):
      - "calls": this method calls target_fqn (another method)
      - "extends": class extends another class
      - "implements": class implements an interface
      - "field-access": reads/writes a field
    """

    target_fqn: str
    kind: str
    line: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> DependencyEdge:
        return cls(target_fqn=d["target_fqn"], kind=d["kind"], line=int(d["line"]))


@dataclass(frozen=True)
class SemanticNode:
    """A resolved-types description of a single declared symbol.

    See module docstring for field policy.
    """

    fqn: str
    kind: str
    signature: str
    resolved_param_types: tuple[str, ...]
    resolved_return_type: str | None
    dependency_edges: tuple[DependencyEdge, ...]
    source_location: SourceLocation

    def to_dict(self) -> dict[str, Any]:
        return {
            "fqn": self.fqn,
            "kind": self.kind,
            "signature": self.signature,
            "resolved_param_types": list(self.resolved_param_types),
            "resolved_return_type": self.resolved_return_type,
            "dependency_edges": [e.to_dict() for e in self.dependency_edges],
            "source_location": self.source_location.to_dict(),
        }

    def to_json(self) -> str:
        """Deterministic JSON serialization (sorted keys). Required for receipt signing."""
        return json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> SemanticNode:
        return cls(
            fqn=d["fqn"],
            kind=d["kind"],
            signature=d["signature"],
            resolved_param_types=tuple(d.get("resolved_param_types", [])),
            resolved_return_type=d.get("resolved_return_type"),
            dependency_edges=tuple(DependencyEdge.from_dict(e) for e in d.get("dependency_edges", [])),
            source_location=SourceLocation.from_dict(d["source_location"]),
        )

    @classmethod
    def from_json(cls, s: str) -> SemanticNode:
        return cls.from_dict(json.loads(s))
