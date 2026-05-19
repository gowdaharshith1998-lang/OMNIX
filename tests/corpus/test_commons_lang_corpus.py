"""Verify the vendored Commons Lang test-corpus parses cleanly via the
real JavaParser bridge.

The corpus is a trimmed subset (see tests/corpus/COMMONS_LANG_LICENSE.md);
this test guards against future trimmer mistakes that would leave
unresolvable symbols and break the M1 Phase 6 E2E rebuild flow.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnix.semantic.java.parser import JAR_PATH, parse_file

_CORPUS_DIR = Path(__file__).resolve().parent / "commons_lang"
_STRING_UTILS = _CORPUS_DIR / "StringUtils.java"
_FULL_CORPUS_DIR = Path(__file__).resolve().parent / "commons_lang_full"
_FULL_STRING_UTILS = (
    _FULL_CORPUS_DIR / "org" / "apache" / "commons" / "lang" / "StringUtils.java"
)

# The corpus tests need the vendored emitter JAR; mirror the gate pattern
# used by the existing tests/semantic/java/* xfail tripwires.
_NO_JAR = pytest.mark.skipif(
    not JAR_PATH.exists(),
    reason="vendored emitter JAR missing — run scripts/vendor_javaparser.sh",
)


@_NO_JAR
def test_corpus_file_exists() -> None:
    assert _STRING_UTILS.exists(), f"missing corpus file: {_STRING_UTILS}"


@_NO_JAR
def test_license_file_present_and_apache() -> None:
    """COMMONS_LANG_LICENSE.md must attest Apache 2.0 + document the trim."""
    lic = _CORPUS_DIR.parent / "COMMONS_LANG_LICENSE.md"
    assert lic.exists()
    text = lic.read_text(encoding="utf-8")
    assert "Apache License 2.0" in text
    assert "commons-lang:commons-lang:2.6" in text
    assert "trimmed" in text.lower() or "trim" in text.lower()
    assert "commons_lang_full" in text


@_NO_JAR
def test_emitter_resolves_reverse_method() -> None:
    """R-5.3 — the corpus emits a node for the reverse(String) method
    with fully resolved param + return types."""
    nodes = parse_file(_STRING_UTILS)
    reverse = next(
        (n for n in nodes if n.fqn == "org.apache.commons.lang.StringUtils.reverse"),
        None,
    )
    assert reverse is not None, (
        f"missing reverse() node. Got: {[n.fqn for n in nodes]}"
    )
    assert reverse.kind == "method"
    assert reverse.resolved_return_type == "java.lang.String"
    # SemanticNode normalizes resolved_param_types to a tuple for hashability.
    assert tuple(reverse.resolved_param_types) == ("java.lang.String",)


@_NO_JAR
def test_corpus_self_contained_no_unresolved_symbols() -> None:
    """The trim removed everything that referenced Commons-internal types
    — the parse must succeed without UnresolvedSymbolError."""
    # parse_file raises UnresolvedSymbolError on failure (per omnix.semantic.errors);
    # a clean call means all symbols resolved through java.lang.* or the file itself.
    nodes = parse_file(_STRING_UTILS)
    assert len(nodes) >= 1


@_NO_JAR
def test_full_stringutils_source_is_vendored_at_upstream_size() -> None:
    assert _FULL_STRING_UTILS.exists(), f"missing full corpus file: {_FULL_STRING_UTILS}"
    lines = _FULL_STRING_UTILS.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 6594
    assert "public static String[] split(String str, char separatorChar)" in "\n".join(lines)


@_NO_JAR
def test_full_stringutils_source_parses_cleanly() -> None:
    nodes = parse_file(_FULL_STRING_UTILS, timeout_s=60)
    stringutils_nodes = [
        n for n in nodes if n.fqn.startswith("org.apache.commons.lang.StringUtils.")
    ]
    assert len(stringutils_nodes) == 177
    assert any(n.fqn == "org.apache.commons.lang.StringUtils.reverse" for n in nodes)
    assert any(n.fqn == "org.apache.commons.lang.StringUtils.split" for n in nodes)
