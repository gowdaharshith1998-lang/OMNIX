"""Pass 2: Signature — derive canonical signature + modifiers from a SemanticNode.

The SemanticNode already carries a canonical-ish string in `node.signature`
(e.g. `"public static String reverse(String)"`). This pass:

- Echoes the canonical string verbatim.
- Splits the leading tokens to extract Java modifiers (`public`, `private`,
  `protected`, `static`, `final`, `abstract`, `synchronized`, `native`,
  `default`). Anything that isn't a recognized modifier is treated as the
  return-type keyword and ends the modifier scan.
- Carries `resolved_return_type` and `resolved_param_types` through.

No inference of synthetic modifiers (e.g. implied `public` on interface
methods). v1 records what the upstream produced; M2 may refine.
"""

from __future__ import annotations

from omnix.semantic import SemanticNode
from omnix.spec import Signature

# Java modifier keywords recognized by the v1 signature pass. Ordering inside
# this set is not meaningful — emission order follows the source signature.
_JAVA_MODIFIERS: frozenset[str] = frozenset(
    {
        "public",
        "private",
        "protected",
        "static",
        "final",
        "abstract",
        "synchronized",
        "native",
        "default",
    }
)


def _extract_modifiers(canonical: str) -> tuple[str, ...]:
    """Pull leading modifier tokens off the canonical signature.

    Stops at the first token that isn't a known modifier — that token is the
    return-type keyword (or the method/identifier itself for constructors). We
    deliberately do not validate balance of `(...)` here; that's the parser's
    job upstream.
    """
    if not canonical:
        return ()
    head = canonical.split("(", 1)[0]  # drop param list before tokenizing
    tokens = head.split()
    modifiers: list[str] = []
    for token in tokens:
        if token in _JAVA_MODIFIERS:
            modifiers.append(token)
        else:
            break
    return tuple(modifiers)


def run(node: SemanticNode) -> Signature:
    """Build a Signature from the SemanticNode's already-canonical string."""
    canonical = node.signature
    modifiers = _extract_modifiers(canonical)
    return Signature(
        canonical=canonical,
        modifiers=modifiers,
        return_type=node.resolved_return_type,
        param_types=tuple(node.resolved_param_types),
    )
