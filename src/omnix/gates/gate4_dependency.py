"""Gate 4 — dependency reference comparison.

R-6.2 forbids skipping this gate even when gates 1-3 already failed: LLMs
hallucinate API calls that compile and type-check but reference symbols the spec
never asked for. Comparing the spec's declared dependencies against the rebuilt
source's method-call / import references catches those.

Acceptance rule (Pass-4 echo): a spec dependency is satisfied if EITHER the
legacy `target_fqn` appears in the rebuilt source OR the dep's `rebuilt_signature`
(if populated) appears. Anything in the source not declared in the spec is logged
as `extra`.

Gap with real parser (recorded for M1 Phase 6 dispatch):
- We match on token presence (FQN substring or trailing segment as a bare call).
  We do not do call-graph resolution, so a string literal that happens to contain
  `java.lang.String.length` would falsely satisfy that dep. The real implementation
  will use the JavaParser symbol-solver edges from the semantic layer.
"""

from __future__ import annotations

import re

from omnix.gates.result import GateError
from omnix.spec import DependencyRef

_GATE_NUMBER = 4
_GATE_NAME = "dependency"

_IMPORT_RE = re.compile(r"^\s*import\s+(?:static\s+)?([\w.$]+(?:\.\*)?)\s*;\s*$", re.MULTILINE)
_CALL_RE = re.compile(r"([\w.$]+)\s*\(")


def _references_in_source(source_code: str) -> set[str]:
    """Collect FQN-like tokens that appear in the source.

    Returns both fully-qualified (`a.b.C.method`) and unqualified
    (`method`) forms — the matcher accepts either.
    """
    found: set[str] = set()

    # Imports — strip trailing `.*` for on-demand imports.
    for match in _IMPORT_RE.finditer(source_code):
        raw = match.group(1).strip()
        if raw.endswith(".*"):
            raw = raw[:-2]
        if raw:
            found.add(raw)

    # Call sites — `foo(`, `Bar.foo(`, `a.b.C.foo(`.
    for match in _CALL_RE.finditer(source_code):
        token = match.group(1).strip()
        if token:
            found.add(token)

    return found


def _is_referenced(target: str, references: set[str], raw_source: str) -> bool:
    """Match a dep target against rebuilt-source references.

    Accepts:
      - exact FQN match (`java.lang.String.length` in references)
      - trailing-segment match (`length` as a bare call or `s.length` receiver)
      - substring presence in raw source (catches `obj.length()` where receiver
        type is bound at runtime)
    """
    if target in references:
        return True
    trailing = target.rsplit(".", 1)[-1]
    if trailing in references:
        return True
    # Match against receiver-style call tokens: any reference ending in `.trailing`.
    for ref in references:
        if ref.endswith("." + trailing):
            return True
    # Last resort: substring match against raw source (catches receiver-dotted
    # calls the call-regex missed).
    return target in raw_source or trailing + "(" in raw_source


def check(
    source_code: str,
    spec_dependencies: tuple[DependencyRef, ...],
) -> GateError | None:
    """Return None on full coverage, GateError listing missing/extra deps."""
    references = _references_in_source(source_code)

    missing: list[str] = []
    missing_have_rebuilt: dict[str, bool] = {}
    declared_targets: set[str] = set()

    for dep in spec_dependencies:
        declared_targets.add(dep.target_fqn)
        if dep.rebuilt_signature is not None:
            declared_targets.add(dep.rebuilt_signature)

        legacy_ok = _is_referenced(dep.target_fqn, references, source_code)
        rebuilt_ok = (
            dep.rebuilt_signature is not None
            and _is_referenced(dep.rebuilt_signature, references, source_code)
        )
        if not (legacy_ok or rebuilt_ok):
            missing.append(dep.target_fqn)
            missing_have_rebuilt[dep.target_fqn] = dep.rebuilt_signature is not None

    # `extra` = call-site references that don't match any declared target and
    # aren't standard-library / control-flow noise.
    # Conservative noise filter: ignore single-segment, lowercase-start tokens
    # that are common control flow (`if`, `for`, `while`, `switch`, `return`,
    # `new`, `super`, `this`) — those create false positives.
    _NOISE = {"if", "for", "while", "switch", "return", "new", "super", "this", "catch", "synchronized", "assert"}
    extra: list[str] = []
    for ref in references:
        if ref in declared_targets:
            continue
        if ref in _NOISE:
            continue
        # Skip simple unqualified identifiers — too noisy without a call graph.
        # We only report `extra` for fully-qualified references (3+ segments
        # like `com.pkg.Class.method`). 2-segment refs like `s.length` are
        # almost certainly receiver-style instance calls, not foreign deps.
        if ref.count(".") < 2:
            continue
        # Also skip if any declared target's trailing segment matches this ref's
        # trailing — already accounted for via _is_referenced.
        trailing = ref.rsplit(".", 1)[-1]
        if any(t.rsplit(".", 1)[-1] == trailing for t in declared_targets):
            continue
        extra.append(ref)

    if not missing and not extra:
        return None

    parts: list[str] = []
    if missing:
        parts.append(f"missing deps: {missing}")
    if extra:
        parts.append(f"extra deps: {extra}")
    message = "; ".join(parts)

    return GateError(
        gate_number=_GATE_NUMBER,
        gate_name=_GATE_NAME,
        message=message,
        details={
            "missing": sorted(missing),
            "extra": sorted(extra),
            "missing_have_rebuilt": missing_have_rebuilt,
        },
    )
