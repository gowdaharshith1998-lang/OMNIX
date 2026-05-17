"""Spec + sub-dataclasses — wire format from spec generator to LLM orchestrator.

Frozen dataclasses for hashability + value semantics. JSON round-trip is deterministic
(sorted keys) so spec_hash in RebuildAttempt is stable.

Deferred-to-v2 fields are typed Optional[...] = None so the schema is forward-compatible
without requiring a versioned migration when M2 passes start populating them.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class Identity:
    fqn: str
    kind: str  # "method" | "class" | "field"
    source_file: str
    source_line: int

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Signature:
    canonical: str  # e.g. "public static String reverse(String)"
    modifiers: tuple[str, ...]  # ("public", "static")
    return_type: str | None  # FQN or None
    param_types: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "canonical": self.canonical,
            "modifiers": list(self.modifiers),
            "return_type": self.return_type,
            "param_types": list(self.param_types),
        }


@dataclass(frozen=True)
class TypeInfo:
    """Per-parameter and return type structure."""

    param_types: tuple[str, ...]  # FQNs
    return_type: str | None  # FQN or None
    is_return_primitive: bool
    are_params_primitive: tuple[bool, ...]
    generic_args: tuple[tuple[str, ...], ...] = ()  # per-param generic args; empty tuple if none

    def to_dict(self) -> dict[str, Any]:
        return {
            "param_types": list(self.param_types),
            "return_type": self.return_type,
            "is_return_primitive": self.is_return_primitive,
            "are_params_primitive": list(self.are_params_primitive),
            "generic_args": [list(g) for g in self.generic_args],
        }


@dataclass(frozen=True)
class DependencyRef:
    """A dependency in the spec with rebuilt-vs-legacy signature awareness."""

    target_fqn: str
    kind: str  # "calls" | "extends" | "implements" | "field-access"
    legacy_signature: str
    rebuilt_signature: str | None  # populated iff target has been rebuilt

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @property
    def effective_signature(self) -> str:
        """Pass 4 rule: use rebuilt if present, else legacy."""
        return self.rebuilt_signature if self.rebuilt_signature is not None else self.legacy_signature


@dataclass(frozen=True)
class Spec:
    """Rebuild spec for one semantic node.

    v1 (M1) populates: identity, signature, types, dependencies, target_hints.
    v2 (M2) populates the deferred fields below. They serialize as null in v1.
    """

    identity: Identity
    signature: Signature
    types: TypeInfo
    dependencies: tuple[DependencyRef, ...]
    target_hints: tuple[str, ...]

    # v2 (M2) — silently None in v1
    preconditions: tuple[str, ...] | None = None
    postconditions: tuple[str, ...] | None = None
    side_effects: tuple[str, ...] | None = None
    behavioral_properties: tuple[str, ...] | None = None
    edge_cases: tuple[str, ...] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "identity": self.identity.to_dict(),
            "signature": self.signature.to_dict(),
            "types": self.types.to_dict(),
            "dependencies": [d.to_dict() for d in self.dependencies],
            "target_hints": list(self.target_hints),
            "preconditions": list(self.preconditions) if self.preconditions is not None else None,
            "postconditions": list(self.postconditions) if self.postconditions is not None else None,
            "side_effects": list(self.side_effects) if self.side_effects is not None else None,
            "behavioral_properties": (
                list(self.behavioral_properties) if self.behavioral_properties is not None else None
            ),
            "edge_cases": list(self.edge_cases) if self.edge_cases is not None else None,
        }

    def to_json(self, indent: int | None = None) -> str:
        """Deterministic JSON (sorted keys). Required for spec_hash stability."""
        return json.dumps(self.to_dict(), sort_keys=True, indent=indent, separators=(",", ":") if indent is None else None)
