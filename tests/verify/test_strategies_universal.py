from __future__ import annotations

from src.verify import strategies_universal as su


def test_strategy_synthesis_from_rust_signature() -> None:
    s1 = su.synthesize_from_rust_signature("fn foo(x: i32) -> i32 { x }")
    assert "i32" in s1.param_types[0] or s1.param_types[0] == "i32"
    assert s1.native_hint == "cargo_fuzz"
    assert 0 in (x for x in s1.boundary_values if isinstance(x, int))


def test_strategy_synthesis_from_go_signature() -> None:
    g0 = su.synthesize_from_go_signature("func F(a int, b string) error { return nil }")
    assert g0.mode == "native_go"
    assert g0.native_hint == "go_fuzz"
    assert "int" in g0.param_types[0] and "string" in g0.param_types[1]


def test_strategy_synthesis_falls_back_to_llm_for_dynamic() -> None:
    s2 = su.synthesize_dynamic_for_llm("dynamic")
    assert s2.mode == "llm"
    assert not s2.param_types
    a = su.apply_node_metadata(["*dyn Any"])
    assert a.mode in ("llm", "dynamic")
