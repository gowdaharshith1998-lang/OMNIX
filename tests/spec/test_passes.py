"""Per-pass unit tests for omnix.spec.passes."""

from __future__ import annotations

import pytest

from omnix.semantic import DependencyEdge, SemanticNode, SourceLocation
from omnix.spec import DependencyRef, UnsupportedTargetLanguageError
from omnix.spec.passes import dependencies as dependencies_pass
from omnix.spec.passes import identity as identity_pass
from omnix.spec.passes import signature as signature_pass
from omnix.spec.passes import target_hints as target_hints_pass
from omnix.spec.passes import types as types_pass


# ---------------------------------------------------------------------------
# Fixture builder
# ---------------------------------------------------------------------------


def make_node(
    *,
    fqn: str = "org.example.Foo.bar",
    kind: str = "method",
    signature: str = "public String bar(String)",
    resolved_param_types: tuple[str, ...] = ("java.lang.String",),
    resolved_return_type: str | None = "java.lang.String",
    dependency_edges: tuple[DependencyEdge, ...] = (),
    file_path: str = "src/main/java/org/example/Foo.java",
    line: int = 10,
) -> SemanticNode:
    """Build a SemanticNode with sensible defaults for tests."""
    return SemanticNode(
        fqn=fqn,
        kind=kind,
        signature=signature,
        resolved_param_types=resolved_param_types,
        resolved_return_type=resolved_return_type,
        dependency_edges=dependency_edges,
        source_location=SourceLocation(file_path=file_path, line=line),
    )


# ---------------------------------------------------------------------------
# Pass 1: identity
# ---------------------------------------------------------------------------


def test_identity_standard_method() -> None:
    node = make_node(
        fqn="org.apache.commons.lang.StringUtils.reverse",
        kind="method",
        file_path="src/main/java/org/apache/commons/lang/StringUtils.java",
        line=42,
    )
    ident = identity_pass.run(node)
    assert ident.fqn == "org.apache.commons.lang.StringUtils.reverse"
    assert ident.kind == "method"
    assert ident.source_file == "src/main/java/org/apache/commons/lang/StringUtils.java"
    assert ident.source_line == 42


def test_identity_void_method_has_no_special_handling() -> None:
    node = make_node(
        fqn="org.example.Logger.log",
        signature="public void log(String)",
        resolved_return_type=None,
        line=7,
    )
    ident = identity_pass.run(node)
    # void-ness lives in signature/types passes — identity just copies coords.
    assert ident.fqn == "org.example.Logger.log"
    assert ident.source_line == 7
    assert ident.kind == "method"


# ---------------------------------------------------------------------------
# Pass 2: signature
# ---------------------------------------------------------------------------


def test_signature_extracts_public_static_modifiers() -> None:
    node = make_node(signature="public static String reverse(String)")
    sig = signature_pass.run(node)
    assert sig.canonical == "public static String reverse(String)"
    assert sig.modifiers == ("public", "static")
    assert sig.return_type == "java.lang.String"
    assert sig.param_types == ("java.lang.String",)


def test_signature_extracts_private_final_modifiers() -> None:
    node = make_node(
        signature="private final int x()",
        resolved_param_types=(),
        resolved_return_type="int",
    )
    sig = signature_pass.run(node)
    assert sig.modifiers == ("private", "final")
    assert sig.return_type == "int"
    assert sig.param_types == ()


def test_signature_no_modifiers_returns_empty_tuple() -> None:
    # Package-private method: no leading modifier tokens.
    node = make_node(signature="String localOnly()", resolved_param_types=())
    sig = signature_pass.run(node)
    assert sig.modifiers == ()
    assert sig.canonical == "String localOnly()"


def test_signature_stops_modifier_scan_at_return_type() -> None:
    # `synchronized` is a modifier; `Map` is the return type and ends the scan.
    node = make_node(
        signature="public synchronized Map foo(String)",
        resolved_return_type="java.util.Map",
    )
    sig = signature_pass.run(node)
    assert sig.modifiers == ("public", "synchronized")


# ---------------------------------------------------------------------------
# Pass 3: types
# ---------------------------------------------------------------------------


def test_types_primitive_return_and_param() -> None:
    node = make_node(
        signature="public int add(int)",
        resolved_param_types=("int",),
        resolved_return_type="int",
    )
    info = types_pass.run(node)
    assert info.return_type == "int"
    assert info.is_return_primitive is True
    assert info.are_params_primitive == (True,)
    assert info.generic_args == ((),)


def test_types_reference_string_is_not_primitive() -> None:
    node = make_node(
        signature="public String reverse(String)",
        resolved_param_types=("java.lang.String",),
        resolved_return_type="java.lang.String",
    )
    info = types_pass.run(node)
    assert info.is_return_primitive is False
    assert info.are_params_primitive == (False,)
    assert info.generic_args == ((),)


def test_types_void_return_is_primitive_per_jls() -> None:
    node = make_node(
        signature="public void log(String)",
        resolved_return_type="void",
    )
    info = types_pass.run(node)
    assert info.is_return_primitive is True


def test_types_parses_generic_args_for_parameterized_param() -> None:
    node = make_node(
        signature="public void process(List<String>)",
        resolved_param_types=("java.util.List<java.lang.String>",),
        resolved_return_type="void",
    )
    info = types_pass.run(node)
    assert info.are_params_primitive == (False,)
    assert info.generic_args == (("java.lang.String",),)


def test_types_parses_multi_arg_generics_at_depth_zero() -> None:
    # Map<String, List<Integer>>: top-level args are String + List<Integer>.
    node = make_node(
        signature="public void load(Map)",
        resolved_param_types=("java.util.Map<java.lang.String, java.util.List<java.lang.Integer>>",),
        resolved_return_type="void",
    )
    info = types_pass.run(node)
    assert info.generic_args == (
        ("java.lang.String", "java.util.List<java.lang.Integer>"),
    )


# ---------------------------------------------------------------------------
# Pass 4: dependencies
# ---------------------------------------------------------------------------


class _StubGraph:
    def __init__(self, rebuilt: dict[str, str], legacy: dict[str, str]) -> None:
        self._rebuilt = rebuilt
        self._legacy = legacy

    def get_rebuilt_signature(self, fqn: str) -> str | None:
        return self._rebuilt.get(fqn)

    def get_legacy_signature(self, fqn: str) -> str:
        return self._legacy.get(fqn, "")


def test_dependencies_populates_rebuilt_when_known_else_none() -> None:
    node = make_node(
        dependency_edges=(
            DependencyEdge(target_fqn="org.example.A.foo", kind="calls", line=11),
            DependencyEdge(target_fqn="org.example.B.bar", kind="calls", line=12),
        ),
    )
    graph = _StubGraph(
        rebuilt={"org.example.A.foo": "public String foo()"},
        legacy={
            "org.example.A.foo": "public java.lang.String foo()",
            "org.example.B.bar": "public void bar()",
        },
    )
    refs = dependencies_pass.run(node, graph)
    assert len(refs) == 2
    assert refs[0] == DependencyRef(
        target_fqn="org.example.A.foo",
        kind="calls",
        legacy_signature="public java.lang.String foo()",
        rebuilt_signature="public String foo()",
    )
    assert refs[1].rebuilt_signature is None
    assert refs[1].legacy_signature == "public void bar()"
    # effective_signature contract: rebuilt-or-legacy.
    assert refs[0].effective_signature == "public String foo()"
    assert refs[1].effective_signature == "public void bar()"


def test_dependencies_missing_legacy_falls_back_to_empty_string() -> None:
    node = make_node(
        dependency_edges=(
            DependencyEdge(target_fqn="org.unknown.X.y", kind="calls", line=3),
        ),
    )
    graph = _StubGraph(rebuilt={}, legacy={})
    refs = dependencies_pass.run(node, graph)
    assert refs[0].legacy_signature == ""
    assert refs[0].rebuilt_signature is None


def test_dependencies_empty_when_node_has_no_edges() -> None:
    node = make_node(dependency_edges=())
    graph = _StubGraph(rebuilt={}, legacy={})
    assert dependencies_pass.run(node, graph) == ()


# ---------------------------------------------------------------------------
# Pass 5: target_hints
# ---------------------------------------------------------------------------


def test_target_hints_java21_returns_8_in_order() -> None:
    hints = target_hints_pass.run("java21")
    assert len(hints) == 8
    assert hints[0].startswith("Use `var`")
    assert hints[1].startswith("Prefer records")
    assert hints[-1] == "Avoid raw types; always parameterize generics"
    # Constant is exposed for orchestrators that want it directly.
    assert hints is target_hints_pass.JAVA21_HINTS


def test_target_hints_unsupported_language_raises() -> None:
    with pytest.raises(UnsupportedTargetLanguageError) as exc:
        target_hints_pass.run("cobol")
    assert exc.value.target_language == "cobol"
