"""Pure contract tests for the Spec / sub-dataclass shapes.

These are deliberately decoupled from the passes — they assert the wire-format
guarantees the orchestrator and receipt-signer rely on (frozenness,
effective_signature semantics, JSON determinism).
"""

from __future__ import annotations

import dataclasses
import json

import pytest

from omnix.spec import DependencyRef, Identity, Signature, Spec, TypeInfo


def _make_spec() -> Spec:
    return Spec(
        identity=Identity(
            fqn="org.example.Foo.bar",
            kind="method",
            source_file="src/main/java/org/example/Foo.java",
            source_line=10,
        ),
        signature=Signature(
            canonical="public String bar(String)",
            modifiers=("public",),
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
        dependencies=(
            DependencyRef(
                target_fqn="org.example.B.baz",
                kind="calls",
                legacy_signature="public void baz()",
                rebuilt_signature=None,
            ),
        ),
        target_hints=("hint-a", "hint-b"),
    )


def test_spec_is_frozen() -> None:
    spec = _make_spec()
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.target_hints = ("mutated",)  # type: ignore[misc]


def test_identity_signature_typeinfo_dependencyref_all_frozen() -> None:
    spec = _make_spec()
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.identity.fqn = "mutated"  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.signature.modifiers = ()  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.types.return_type = None  # type: ignore[misc]
    with pytest.raises(dataclasses.FrozenInstanceError):
        spec.dependencies[0].kind = "extends"  # type: ignore[misc]


def test_dependency_ref_effective_signature_prefers_rebuilt() -> None:
    rebuilt = DependencyRef(
        target_fqn="x", kind="calls", legacy_signature="legacy()", rebuilt_signature="rebuilt()"
    )
    assert rebuilt.effective_signature == "rebuilt()"


def test_dependency_ref_effective_signature_falls_back_to_legacy() -> None:
    legacy_only = DependencyRef(
        target_fqn="x", kind="calls", legacy_signature="legacy()", rebuilt_signature=None
    )
    assert legacy_only.effective_signature == "legacy()"


def test_dependency_ref_effective_signature_handles_empty_legacy() -> None:
    blank = DependencyRef(target_fqn="x", kind="calls", legacy_signature="", rebuilt_signature=None)
    assert blank.effective_signature == ""


def test_to_dict_round_trips_via_json_deterministically() -> None:
    spec = _make_spec()
    j1 = spec.to_json()
    j2 = spec.to_json()
    assert j1 == j2
    parsed1 = json.loads(j1)
    parsed2 = json.loads(j2)
    assert parsed1 == parsed2
    # sort_keys=True top-level guarantee.
    assert list(parsed1.keys()) == sorted(parsed1.keys())


def test_to_json_indent_produces_pretty_output() -> None:
    spec = _make_spec()
    pretty = spec.to_json(indent=2)
    assert "\n" in pretty
    # Indented output still parses to the same dict as compact.
    assert json.loads(pretty) == json.loads(spec.to_json())


def test_to_dict_lists_match_tuple_fields() -> None:
    """to_dict converts internal tuples to lists for JSON-friendliness."""
    spec = _make_spec()
    d = spec.to_dict()
    assert isinstance(d["target_hints"], list)
    assert isinstance(d["signature"]["modifiers"], list)
    assert isinstance(d["types"]["param_types"], list)
