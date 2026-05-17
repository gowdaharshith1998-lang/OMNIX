"""Tests for omnix.orchestrator.prompt_template.

Covers determinism (load-bearing for receipts), version pinning, and the
basic SYSTEM/SPEC/SOURCE layout.
"""

from __future__ import annotations

import re

from omnix.orchestrator.prompt_template import (
    PROMPT_TEMPLATE_VERSION,
    SYSTEM_PROMPT,
    format_prompt,
    format_scc_prompt,
)
from omnix.spec import DependencyRef, Identity, Signature, Spec, TypeInfo


def _make_spec(fqn: str = "com.example.Foo.bar") -> Spec:
    return Spec(
        identity=Identity(fqn=fqn, kind="method", source_file="Foo.java", source_line=1),
        signature=Signature(
            canonical="public static String bar(String)",
            modifiers=("public", "static"),
            return_type="java.lang.String",
            param_types=("java.lang.String",),
        ),
        types=TypeInfo(
            param_types=("java.lang.String",),
            return_type="java.lang.String",
            is_return_primitive=False,
            are_params_primitive=(False,),
            generic_args=((),),
        ),
        dependencies=(),
        target_hints=("Use var for local variable type inference",),
    )


def test_prompt_includes_spec_and_source() -> None:
    spec = _make_spec()
    source = "public static String bar(String s) { return s; }"
    text, _hash = format_prompt(spec, source)

    assert SYSTEM_PROMPT in text
    # Spec JSON must appear — check on a distinctive substring.
    assert '"fqn": "com.example.Foo.bar"' in text
    assert source in text
    # Layout markers.
    assert "[SYSTEM]" in text
    assert "[SPEC]" in text
    assert "[SOURCE]" in text
    assert "```java" in text


def test_prompt_hash_is_deterministic() -> None:
    spec = _make_spec()
    source = "public static String bar(String s) { return s; }"
    _, hash_one = format_prompt(spec, source)
    _, hash_two = format_prompt(spec, source)
    assert hash_one == hash_two
    # SHA-256 hex = 64 chars.
    assert len(hash_one) == 64
    assert re.fullmatch(r"[0-9a-f]{64}", hash_one)


def test_prompt_hash_changes_with_spec() -> None:
    spec_a = _make_spec(fqn="com.example.Foo.bar")
    spec_b = _make_spec(fqn="com.example.Foo.baz")
    source = "public static String bar(String s) { return s; }"
    _, hash_a = format_prompt(spec_a, source)
    _, hash_b = format_prompt(spec_b, source)
    assert hash_a != hash_b


def test_prompt_hash_changes_with_source() -> None:
    spec = _make_spec()
    _, hash_a = format_prompt(spec, "return s;")
    _, hash_b = format_prompt(spec, "return s.toUpperCase();")
    assert hash_a != hash_b


def test_prompt_template_version_constant() -> None:
    assert isinstance(PROMPT_TEMPLATE_VERSION, str)
    assert PROMPT_TEMPLATE_VERSION
    assert re.fullmatch(r"v\d+-\d{4}-\d{2}-\d{2}", PROMPT_TEMPLATE_VERSION)


def test_scc_prompt_includes_all_members() -> None:
    spec_a = _make_spec(fqn="com.example.A.one")
    spec_b = _make_spec(fqn="com.example.A.two")
    text, hash_ = format_scc_prompt(
        [spec_a, spec_b],
        {"com.example.A.one": "void one() { two(); }", "com.example.A.two": "void two() { one(); }"},
    )
    assert SYSTEM_PROMPT in text
    assert "com.example.A.one" in text
    assert "com.example.A.two" in text
    assert "void one() { two(); }" in text
    assert "void two() { one(); }" in text
    assert len(hash_) == 64
