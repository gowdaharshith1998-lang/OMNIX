"""Unit tests for SemanticNode / DependencyEdge / SourceLocation contracts.

These tests pin the wire format that the Java emitter and downstream
consumers (omnix.spec, omnix.gates) both depend on. Determinism is required
for receipt signing — any change here must be deliberate.
"""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from omnix.semantic import DependencyEdge, SemanticNode, SourceLocation


def _make_node(
    *,
    fqn: str = "org.apache.commons.lang.StringUtils.reverse",
    kind: str = "method",
    signature: str = "public static String reverse(String)",
    resolved_param_types: tuple[str, ...] = ("java.lang.String",),
    resolved_return_type: str | None = "java.lang.String",
    dependency_edges: tuple[DependencyEdge, ...] = (),
    source_location: SourceLocation | None = None,
) -> SemanticNode:
    return SemanticNode(
        fqn=fqn,
        kind=kind,
        signature=signature,
        resolved_param_types=resolved_param_types,
        resolved_return_type=resolved_return_type,
        dependency_edges=dependency_edges,
        source_location=source_location
        or SourceLocation(file_path="StringUtils.java", line=12, column=5),
    )


def test_semantic_node_round_trip() -> None:
    node = _make_node()
    restored = SemanticNode.from_json(node.to_json())
    assert restored == node


def test_semantic_node_deterministic_serialization() -> None:
    node = _make_node(
        dependency_edges=(
            DependencyEdge(target_fqn="java.lang.StringBuilder.append", kind="calls", line=17),
            DependencyEdge(target_fqn="java.lang.String.charAt", kind="calls", line=17),
        )
    )
    first = node.to_json()
    second = node.to_json()
    assert first == second
    # sorted-keys invariant: the top-level field order is alphabetical.
    # Compare on top-level keys only (nested "kind" appears inside edges).
    top_level = [
        "dependency_edges",
        "fqn",
        "kind",
        "resolved_param_types",
        "resolved_return_type",
        "signature",
        "source_location",
    ]
    # JSON has no `,"<key>":` prefix on the first key, so anchor to the start
    # of the document and use `"<key>":` as the unique top-level anchor.
    last_pos = -1
    for key in top_level:
        # rfind+find both work since each top-level key appears at most once
        # before any nested duplicate of the same name (top-level alphabetical
        # order guarantees this for "kind" specifically).
        pos = first.find(f'"{key}":', last_pos + 1)
        assert pos > last_pos, f"top-level key {key!r} out of order in {first!r}"
        last_pos = pos


def test_semantic_node_with_dependency_edges() -> None:
    edges = (
        DependencyEdge(target_fqn="java.lang.StringBuilder.append", kind="calls", line=17),
        DependencyEdge(target_fqn="java.lang.String.charAt", kind="calls", line=17),
        DependencyEdge(target_fqn="java.lang.StringBuilder.toString", kind="calls", line=19),
    )
    node = _make_node(dependency_edges=edges)
    restored = SemanticNode.from_json(node.to_json())
    assert restored.dependency_edges == edges
    assert len(restored.dependency_edges) == 3


def test_dependency_edge_round_trip() -> None:
    edge = DependencyEdge(
        target_fqn="java.lang.StringBuilder.append", kind="calls", line=17
    )
    restored = DependencyEdge.from_dict(edge.to_dict())
    assert restored == edge


def test_source_location_round_trip() -> None:
    loc = SourceLocation(file_path="src/main/java/StringUtils.java", line=42, column=8)
    restored = SourceLocation.from_dict(loc.to_dict())
    assert restored == loc
    # default column is 0
    bare = SourceLocation(file_path="X.java", line=1)
    assert bare.column == 0
    assert SourceLocation.from_dict(bare.to_dict()) == bare


def test_semantic_node_void_return() -> None:
    node = _make_node(
        fqn="org.example.Logger.log",
        signature="public void log(String)",
        resolved_return_type=None,
    )
    payload = node.to_json()
    restored = SemanticNode.from_json(payload)
    assert restored.resolved_return_type is None
    assert restored == node


def test_semantic_node_zero_param() -> None:
    node = _make_node(
        fqn="org.example.Greeter.hello",
        signature="public String hello()",
        resolved_param_types=(),
        resolved_return_type="java.lang.String",
    )
    restored = SemanticNode.from_json(node.to_json())
    assert restored.resolved_param_types == ()
    assert restored == node


def test_semantic_node_is_frozen() -> None:
    node = _make_node()
    with pytest.raises(FrozenInstanceError):
        node.fqn = "mutated"  # type: ignore[misc]
    edge = DependencyEdge(target_fqn="x", kind="calls", line=1)
    with pytest.raises(FrozenInstanceError):
        edge.line = 2  # type: ignore[misc]
    loc = SourceLocation(file_path="X.java", line=1, column=0)
    with pytest.raises(FrozenInstanceError):
        loc.line = 99  # type: ignore[misc]
