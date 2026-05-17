"""Spec generator v1 — assemble a Spec from a SemanticNode + GraphStore.

Orchestrates the 5 M1 passes:

  1. identity      — fqn / kind / source coordinates
  2. signature     — canonical signature + modifiers + types
  3. types         — primitive vs reference + generic args
  4. dependencies  — outgoing edges with rebuilt-vs-legacy signatures
  5. target_hints  — language idiom hints (Java 21 only in M1)

Deferred-to-M2 fields (preconditions, postconditions, side_effects,
behavioral_properties, edge_cases) are explicitly populated as `None` so the
emitted JSON is forward-compatible with the M2 schema additions.
"""

from __future__ import annotations

from typing import Any

from omnix.semantic import SemanticNode
from omnix.spec import Spec, UnsupportedTargetLanguageError
from omnix.spec.passes import dependencies as _dependencies
from omnix.spec.passes import identity as _identity
from omnix.spec.passes import signature as _signature
from omnix.spec.passes import target_hints as _target_hints
from omnix.spec.passes import types as _types

_SUPPORTED_TARGETS: frozenset[str] = frozenset({"java21"})


def generate(node: SemanticNode, graph_db: Any, target_language: str = "java21") -> Spec:
    """Generate a v1 Spec for `node`.

    Validates `target_language` first so an unsupported target fails fast
    before doing any pass work.
    """
    if target_language not in _SUPPORTED_TARGETS:
        raise UnsupportedTargetLanguageError(target_language)

    identity = _identity.run(node)
    signature = _signature.run(node)
    types = _types.run(node)
    dependencies = _dependencies.run(node, graph_db)
    hints = _target_hints.run(target_language)

    return Spec(
        identity=identity,
        signature=signature,
        types=types,
        dependencies=dependencies,
        target_hints=hints,
        # v2 (M2) — explicit None preserves schema forward-compat.
        preconditions=None,
        postconditions=None,
        side_effects=None,
        behavioral_properties=None,
        edge_cases=None,
    )
