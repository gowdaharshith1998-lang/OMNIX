"""omnix.semantic — language semantic-layer producers.

Contracts here are intentionally lean for M1; see node.py SemanticNode docstring
for the v1-subject-to-revision schema policy. Wire-format is consumed by
omnix.spec (rebuild specs) and omnix.gates (verification).
"""

from omnix.semantic.errors import (
    JavaSemanticError,
    JavaSemanticTimeoutError,
    UnresolvedSymbolError,
)
from omnix.semantic.node import DependencyEdge, SemanticNode, SourceLocation

__all__ = [
    "DependencyEdge",
    "JavaSemanticError",
    "JavaSemanticTimeoutError",
    "SemanticNode",
    "SourceLocation",
    "UnresolvedSymbolError",
]
