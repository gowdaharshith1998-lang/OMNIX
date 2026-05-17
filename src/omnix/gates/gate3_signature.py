"""Gate 3 — signature comparison.

Extract the method signature from the rebuilt source and compare against
`spec.signature.canonical`. R-6.5 requires a unified diff for evidence.

Gap with real parser (recorded for M1 Phase 6 dispatch):
- Regex extraction handles flat parameter lists like `(String s, int n)` but
  cannot accurately split nested generics like `(Map<String, List<Integer>> m)`.
  The xfail test `test_signature_extraction_uses_real_parser_for_generics`
  records this gap explicitly. Until the JAR ships, the heuristic returns a
  whitespace-normalized form that compares well for non-generic signatures.
"""

from __future__ import annotations

import difflib
import re

from omnix.gates.result import GateError
from omnix.spec import Signature

_GATE_NUMBER = 3
_GATE_NAME = "signature"

# Modifiers we recognize when extracting. Order in canonical form follows the
# input source order — we don't normalize ordering today (gap).
_KNOWN_MODIFIERS = ("public", "protected", "private", "static", "final", "abstract", "synchronized", "native", "default")

# Catches `modifiers... return_type name(params) {` for a method declaration.
# Deliberately conservative — we only support one signature per source for the
# rebuilt-method scaffolding case.
_METHOD_RE = re.compile(
    r"""
    (?P<mods>(?:\b(?:public|protected|private|static|final|abstract|synchronized|native|default)\b\s*)*)
    (?P<ret>[\w.$<>\[\]?,\s]+?)
    \s+
    (?P<name>[a-zA-Z_$][\w$]*)
    \s*\(
    (?P<params>[^)]*)
    \)
    \s*(?:throws\s+[\w.,\s]+)?
    \s*\{
    """,
    re.VERBOSE | re.MULTILINE,
)


def _extract_signature(source_code: str) -> dict[str, object] | None:
    """Return {modifiers, return_type, name, params, canonical} or None if no match."""
    match = _METHOD_RE.search(source_code)
    if match is None:
        return None

    mods_raw = match.group("mods").strip()
    modifiers = tuple(m for m in mods_raw.split() if m in _KNOWN_MODIFIERS)
    return_type = match.group("ret").strip()
    name = match.group("name").strip()
    params_raw = match.group("params").strip()

    param_types: tuple[str, ...] = ()
    if params_raw:
        # Naive split: works for flat params, breaks for nested generics (documented gap).
        pieces = [p.strip() for p in params_raw.split(",")]
        types: list[str] = []
        for piece in pieces:
            # Strip annotations like `@Nullable`.
            tokens = [t for t in piece.split() if not t.startswith("@")]
            if not tokens:
                continue
            # Last token is param name; everything before is the type.
            if len(tokens) == 1:
                types.append(tokens[0])
            else:
                types.append(" ".join(tokens[:-1]))
        param_types = tuple(types)

    canonical_parts: list[str] = []
    if modifiers:
        canonical_parts.append(" ".join(modifiers))
    canonical_parts.append(return_type)
    canonical_parts.append(f"{name}({', '.join(param_types)})")
    canonical = " ".join(canonical_parts)

    return {
        "modifiers": modifiers,
        "return_type": return_type,
        "name": name,
        "param_types": param_types,
        "canonical": canonical,
    }


def _normalize(s: str) -> str:
    """Collapse runs of whitespace to a single space, strip trailing/leading whitespace."""
    return re.sub(r"\s+", " ", s).strip()


def check(source_code: str, spec_signature: Signature) -> GateError | None:
    """Return None if extracted signature matches spec, GateError on mismatch."""
    extracted = _extract_signature(source_code)
    expected_norm = _normalize(spec_signature.canonical)

    if extracted is None:
        diff = "\n".join(
            difflib.unified_diff(
                [expected_norm],
                ["<no method signature found>"],
                fromfile="expected",
                tofile="actual",
                lineterm="",
            )
        )
        return GateError(
            gate_number=_GATE_NUMBER,
            gate_name=_GATE_NAME,
            message="no method signature found in rebuilt source",
            details={
                "expected": spec_signature.canonical,
                "actual": None,
                "normalized_diff": diff,
            },
        )

    actual_canonical = str(extracted["canonical"])
    actual_norm = _normalize(actual_canonical)

    if actual_norm == expected_norm:
        return None

    diff = "\n".join(
        difflib.unified_diff(
            [expected_norm],
            [actual_norm],
            fromfile="expected",
            tofile="actual",
            lineterm="",
        )
    )

    return GateError(
        gate_number=_GATE_NUMBER,
        gate_name=_GATE_NAME,
        message=f"signature mismatch: expected {expected_norm!r}, actual {actual_norm!r}",
        details={
            "expected": spec_signature.canonical,
            "actual": actual_canonical,
            "normalized_diff": diff,
        },
    )
