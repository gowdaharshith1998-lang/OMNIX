"""Tests for gate3_signature — heuristic regex extraction + xfail real-parser case."""

from __future__ import annotations

import pytest

from omnix.gates import gate3_signature
from omnix.spec import Signature


def _sig(canonical: str, modifiers: tuple[str, ...], return_type: str | None, params: tuple[str, ...]) -> Signature:
    return Signature(
        canonical=canonical,
        modifiers=modifiers,
        return_type=return_type,
        param_types=params,
    )


def test_extracts_signature_matching_spec() -> None:
    src = """
    public class StringUtils {
        public static String reverse(String s) {
            return new StringBuilder(s).reverse().toString();
        }
    }
    """
    spec = _sig(
        canonical="public static String reverse(String)",
        modifiers=("public", "static"),
        return_type="String",
        params=("String",),
    )
    err = gate3_signature.check(src, spec)
    assert err is None


def test_signature_mismatch_diff_includes_missing_static() -> None:
    # source has `public String reverse(String)` — missing `static`.
    src = """
    public class StringUtils {
        public String reverse(String s) { return s; }
    }
    """
    spec = _sig(
        canonical="public static String reverse(String)",
        modifiers=("public", "static"),
        return_type="String",
        params=("String",),
    )
    err = gate3_signature.check(src, spec)
    assert err is not None
    assert err.gate_number == 3
    assert err.gate_name == "signature"
    assert err.details["expected"] == "public static String reverse(String)"
    assert "static" in err.details["normalized_diff"]


def test_param_type_mismatch() -> None:
    src = "class X { public String reverse(int n) { return null; } }"
    spec = _sig(
        canonical="public String reverse(String)",
        modifiers=("public",),
        return_type="String",
        params=("String",),
    )
    err = gate3_signature.check(src, spec)
    assert err is not None
    assert "int" in err.details["actual"]
    assert "String" in err.details["expected"]


def test_return_type_mismatch() -> None:
    src = "class X { public int reverse(String s) { return 0; } }"
    spec = _sig(
        canonical="public String reverse(String)",
        modifiers=("public",),
        return_type="String",
        params=("String",),
    )
    err = gate3_signature.check(src, spec)
    assert err is not None
    assert "int" in err.details["actual"]
    assert "String" in err.details["expected"]


def test_missing_method_in_source() -> None:
    src = "class X {}"
    spec = _sig(
        canonical="public String reverse(String)",
        modifiers=("public",),
        return_type="String",
        params=("String",),
    )
    err = gate3_signature.check(src, spec)
    assert err is not None
    assert err.details["actual"] is None
    assert "no method signature found" in err.message


def test_visibility_mismatch() -> None:
    src = "class X { private String reverse(String s) { return s; } }"
    spec = _sig(
        canonical="public String reverse(String)",
        modifiers=("public",),
        return_type="String",
        params=("String",),
    )
    err = gate3_signature.check(src, spec)
    assert err is not None
    # Diff should mention both visibilities so reviewers can spot the gap.
    diff = err.details["normalized_diff"]
    assert "public" in diff
    assert "private" in diff


def test_name_mismatch() -> None:
    src = "class X { public String backwards(String s) { return s; } }"
    spec = _sig(
        canonical="public String reverse(String)",
        modifiers=("public",),
        return_type="String",
        params=("String",),
    )
    err = gate3_signature.check(src, spec)
    assert err is not None
    assert "reverse" in err.details["expected"]
    assert "backwards" in err.details["actual"]


def test_whitespace_normalization_passes() -> None:
    # Spec canonical has single spaces, source has extra whitespace — should still pass.
    src = "class X { public  static    String   reverse(  String   s  ) { return s; } }"
    spec = _sig(
        canonical="public static String reverse(String)",
        modifiers=("public", "static"),
        return_type="String",
        params=("String",),
    )
    err = gate3_signature.check(src, spec)
    assert err is None


@pytest.mark.xfail(strict=True, reason="regex param-splitter cannot handle nested generics — needs real parser")
def test_signature_extraction_uses_real_parser_for_generics() -> None:
    # Source has TWO params, both with internal-comma generics. Naive comma-split
    # fragments each into 2 pieces — heuristic sees 4 params, spec lists 2.
    # The broken split's rejoin can't accidentally reproduce the spec because
    # the modifier set + param COUNT diverges.
    src = "class X { public void merge(Map<String, Integer> a, Map<String, Long> b) {} }"
    spec = _sig(
        # Spec lists 2 params separated by ` | ` (explicit non-comma delimiter)
        # so the canonical can never be accidentally produced by the splitter.
        canonical="public void merge(Map<String, Integer> | Map<String, Long>)",
        modifiers=("public",),
        return_type="void",
        params=("Map<String, Integer>", "Map<String, Long>"),
    )
    err = gate3_signature.check(src, spec)
    assert err is None
