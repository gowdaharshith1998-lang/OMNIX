"""JVM-dependent tests for `omnix.semantic.java.parser.parse_file`.

The vendored JavaParser JAR ships alongside source (see
`src/omnix/semantic/java/vendor/SHA256SUMS`). These tests exercise the full
JVM round-trip: subprocess invocation, JSON emission, error sentinel parsing.

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
BAD_CLASSPATH_FIXTURE = Path(__file__).parent / "fixtures" / "BadImport.java"


def test_parse_file_returns_semantic_nodes() -> None:
    """R-3.1: parse_file returns a non-empty list of SemanticNode."""
    nodes = parse_file(FIXTURE)
    assert isinstance(nodes, list)
    assert nodes, "expected at least one SemanticNode from StringUtils.java"
    assert all(isinstance(n, SemanticNode) for n in nodes)


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


def test_unresolved_symbol_raises_structured_error() -> None:
    """R-3.3: unresolved references surface as UnresolvedSymbolError, not silent.

    BadImport.java references `com.nonexistent.NotARealPackage` which is not on
    the JVM bootstrap classpath, so symbol resolution fails. The emitter MUST
    print the well-known `UnresolvedSymbol:` sentinel + exit 2; parser.py
    converts that to UnresolvedSymbolError with structured fields.
    """
    with pytest.raises(UnresolvedSymbolError) as exc_info:
        parse_file(BAD_CLASSPATH_FIXTURE, classpath=[])
    assert "NotARealPackage" in exc_info.value.symbol


def test_timeout_raises_structured_error() -> None:
    """R-3.5: wall-clock overrun raises JavaSemanticTimeoutError."""
    with pytest.raises(JavaSemanticTimeoutError):
        parse_file(FIXTURE, timeout_s=0.001)


def test_json_roundtrip_through_parse_file() -> None:
    """R-3.2: every emitted node round-trips through SemanticNode.to_json/from_json."""
    nodes = parse_file(FIXTURE)
    for node in nodes:
        assert SemanticNode.from_json(node.to_json()) == node


def test_parse_file_missing_jar_raises_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Failure mode: JAR_PATH points at a non-existent file → clear hint to vendor README."""
    monkeypatch.setattr(
        "omnix.semantic.java.parser.JAR_PATH",
        Path("/nonexistent/javaparser-emitter.jar"),
    )
    with pytest.raises(JavaSemanticError) as exc_info:
        parse_file(FIXTURE)
    msg = str(exc_info.value)
    assert "JAR missing" in msg
    assert "vendor" in msg
