"""omnix.spec — per-node rebuild specs consumed by the LLM orchestrator.

5 tractable passes ship in M1 (identity, signature, types, dependencies, target_hints).
Deferred to M2 (each requires symbolic exec / pointer analysis / concolic exec):
- preconditions
- postconditions
- side_effects
- behavioral_properties
- edge_cases
"""

from omnix.spec.errors import UnsupportedTargetLanguageError
from omnix.spec.spec import DependencyRef, Identity, Signature, Spec, TypeInfo

__all__ = [
    "DependencyRef",
    "Identity",
    "Signature",
    "Spec",
    "TypeInfo",
    "UnsupportedTargetLanguageError",
]
