"""JVM-dependent tests for `omnix.semantic.java.parser.parse_file`.

Most of these are tripwires (`xfail(strict=True)`): they describe behavior
that exists in the Java emitter contract but cannot be exercised until the
vendored JAR is on disk. When the JAR lands, every xfail should flip to
XPASS and force a follow-up commit to remove the marker.

EARS clause mapping is recorded in each test name (R-3.x) so the dispatch
spec stays traceable from the test suite.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnix.semantic.errors import (
    JavaSemanticError,
    JavaSemanticTimeoutError,
    UnresolvedSymbolError,
)
from omnix.semantic.java.parser import parse_file
from omnix.semantic.node import SemanticNode

FIXTURE = Path(__file__).parent / "fixtures" / "StringUtils.java"

_XFAIL_NO_JAR = pytest.mark.xfail(
    strict=True,
    reason="vendored JavaParser JAR not present in this session — "
    "see src/omnix/semantic/java/jvm/README.md",
)


@_XFAIL_NO_JAR
def test_parse_file_returns_semantic_nodes() -> None:
    """R-3.1: parse_file returns a non-empty list of SemanticNode."""
    nodes = parse_file(FIXTURE)
    assert isinstance(nodes, list)
    assert nodes, "expected at least one SemanticNode from StringUtils.java"
    assert all(isinstance(n, SemanticNode) for n in nodes)


@_XFAIL_NO_JAR
def test_string_utils_reverse_semantic_node() -> None:
    """R-3.4: reverse(String) emits a SemanticNode with resolved types."""
    nodes = parse_file(FIXTURE)
    reverse_nodes = [n for n in nodes if n.fqn.endswith("reverse")]
    assert reverse_nodes, "no SemanticNode for reverse() found"
    reverse = reverse_nodes[0]
    assert reverse.fqn.endswith("reverse")
    assert "String" in reverse.signature
    assert reverse.resolved_return_type == "java.lang.String"
    assert reverse.resolved_param_types == ("java.lang.String",)


@_XFAIL_NO_JAR
def test_unresolved_symbol_raises_structured_error() -> None:
    """R-3.3: unresolved references surface as UnresolvedSymbolError, not silent."""
    # Source with a deliberately missing classpath dep would trigger this;
    # the fixture itself only touches java.lang.* so this test is a tripwire
    # until a dedicated bad-classpath fixture lands.
    with pytest.raises(UnresolvedSymbolError):
        parse_file(FIXTURE, classpath=[])


@_XFAIL_NO_JAR
def test_timeout_raises_structured_error() -> None:
    """R-3.5: wall-clock overrun raises JavaSemanticTimeoutError."""
    with pytest.raises(JavaSemanticTimeoutError):
        parse_file(FIXTURE, timeout_s=0.001)


@_XFAIL_NO_JAR
def test_json_roundtrip_through_parse_file() -> None:
    """R-3.2: every emitted node round-trips through SemanticNode.to_json/from_json."""
    nodes = parse_file(FIXTURE)
    for node in nodes:
        assert SemanticNode.from_json(node.to_json()) == node


def test_parse_file_missing_jar_raises_clear_error() -> None:
    """Today's testable failure mode: no JAR vendored → JavaSemanticError with hint."""
    with pytest.raises(JavaSemanticError) as exc_info:
        parse_file(FIXTURE)
    msg = str(exc_info.value)
    assert "JAR missing" in msg
    assert "scripts/vendor_javaparser.sh" in msg
