"""End-to-end tests for omnix.spec.generator.generate."""

from __future__ import annotations

import json

import pytest

from omnix.semantic import DependencyEdge, SemanticNode, SourceLocation
from omnix.spec import UnsupportedTargetLanguageError
from omnix.spec.generator import generate


class _StubGraph:
    def __init__(
        self,
        rebuilt: dict[str, str] | None = None,
        legacy: dict[str, str] | None = None,
    ) -> None:
        self._rebuilt = rebuilt or {}
        self._legacy = legacy or {}

    def get_rebuilt_signature(self, fqn: str) -> str | None:
        return self._rebuilt.get(fqn)

    def get_legacy_signature(self, fqn: str) -> str:
        return self._legacy.get(fqn, "")


def _make_string_utils_reverse_node() -> SemanticNode:
    """Fixture: the R-4.7 canonical example — StringUtils.reverse(String)."""
    return SemanticNode(
        fqn="org.apache.commons.lang.StringUtils.reverse",
        kind="method",
        signature="public static String reverse(String)",
        resolved_param_types=("java.lang.String",),
        resolved_return_type="java.lang.String",
        dependency_edges=(
            DependencyEdge(
                target_fqn="java.lang.StringBuilder.reverse",
                kind="calls",
                line=124,
            ),
        ),
        source_location=SourceLocation(
            file_path="src/main/java/org/apache/commons/lang/StringUtils.java",
            line=120,
        ),
    )


def test_generate_returns_spec_with_all_5_passes_populated() -> None:
    node = _make_string_utils_reverse_node()
    graph = _StubGraph(
        rebuilt={"java.lang.StringBuilder.reverse": "public StringBuilder reverse()"},
        legacy={"java.lang.StringBuilder.reverse": "public java.lang.StringBuilder reverse()"},
    )
    spec = generate(node, graph)
    # All 5 M1 fields populated.
    assert spec.identity.fqn == "org.apache.commons.lang.StringUtils.reverse"
    assert spec.signature.canonical == "public static String reverse(String)"
    assert spec.types.return_type == "java.lang.String"
    assert len(spec.dependencies) == 1
    assert len(spec.target_hints) == 8


def test_unsupported_target_raises() -> None:
    node = _make_string_utils_reverse_node()
    with pytest.raises(UnsupportedTargetLanguageError) as exc:
        generate(node, _StubGraph(), target_language="cobol")
    assert exc.value.target_language == "cobol"


def test_deferred_fields_are_none() -> None:
    spec = generate(_make_string_utils_reverse_node(), _StubGraph())
    assert spec.preconditions is None
    assert spec.postconditions is None
    assert spec.side_effects is None
    assert spec.behavioral_properties is None
    assert spec.edge_cases is None


def test_spec_round_trip_via_json() -> None:
    """to_json() is deterministic — same input yields the same string twice,
    and json.loads of either call yields equal dicts."""
    spec = generate(_make_string_utils_reverse_node(), _StubGraph())
    j1 = spec.to_json()
    j2 = spec.to_json()
    assert j1 == j2  # deterministic byte-for-byte
    d1 = json.loads(j1)
    d2 = json.loads(j2)
    assert d1 == d2
    # sort_keys=True: top-level keys come out in sorted order.
    assert list(d1.keys()) == sorted(d1.keys())


def test_spec_for_string_utils_reverse() -> None:
    """R-4.7: spec for org.apache.commons.lang.StringUtils.reverse(String)."""
    spec = generate(_make_string_utils_reverse_node(), _StubGraph())
    assert spec.identity.fqn.endswith(".reverse")
    assert len(spec.target_hints) == 8
    assert spec.types.is_return_primitive is False
