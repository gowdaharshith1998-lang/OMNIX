"""Tests for gate4_dependency — token-based dependency coverage check."""

from __future__ import annotations

from omnix.gates import gate4_dependency
from omnix.spec import DependencyRef


def _dep(target: str, kind: str = "calls", legacy: str = "", rebuilt: str | None = None) -> DependencyRef:
    return DependencyRef(
        target_fqn=target,
        kind=kind,
        legacy_signature=legacy or target,
        rebuilt_signature=rebuilt,
    )


def test_passes_when_all_dependencies_present() -> None:
    src = """
    import java.lang.String;
    class X {
        void f(String s) {
            int n = s.length();
        }
    }
    """
    deps = (
        _dep("java.lang.String"),
        _dep("java.lang.String.length"),
    )
    err = gate4_dependency.check(src, deps)
    assert err is None


def test_fails_when_missing_dependency() -> None:
    # Spec demands `java.lang.String.length`, source doesn't call .length().
    src = "class X { void f() {} }"
    deps = (_dep("java.lang.String.length"),)
    err = gate4_dependency.check(src, deps)
    assert err is not None
    assert err.gate_number == 4
    assert err.gate_name == "dependency"
    assert err.details["missing"] == ["java.lang.String.length"]


def test_fails_with_extra_dependency() -> None:
    # Source calls a fully-qualified method not declared in spec.
    src = """
    class X {
        void f() {
            com.evil.Hidden.exfil();
        }
    }
    """
    deps: tuple[DependencyRef, ...] = ()
    err = gate4_dependency.check(src, deps)
    assert err is not None
    assert any("com.evil.Hidden" in e for e in err.details["extra"])


def test_accepts_rebuilt_signature_alternative() -> None:
    # Spec dep has both legacy + rebuilt. Source uses rebuilt FQN only.
    src = """
    class X {
        void f() {
            com.newpkg.Utils.helper();
        }
    }
    """
    deps = (
        _dep(
            target="com.oldpkg.Utils.helper",
            rebuilt="com.newpkg.Utils.helper",
        ),
    )
    err = gate4_dependency.check(src, deps)
    assert err is None


def test_reports_whether_missing_has_rebuilt() -> None:
    src = "class X { void f() {} }"
    deps = (
        _dep(target="com.a.A.x", rebuilt="com.b.B.x"),  # has rebuilt
        _dep(target="com.c.C.y"),                       # no rebuilt
    )
    err = gate4_dependency.check(src, deps)
    assert err is not None
    have = err.details["missing_have_rebuilt"]
    assert have["com.a.A.x"] is True
    assert have["com.c.C.y"] is False


def test_passes_when_only_legacy_present() -> None:
    # Spec has rebuilt, but source still uses legacy FQN — should still pass.
    src = """
    class X {
        void f() {
            com.oldpkg.Utils.helper();
        }
    }
    """
    deps = (
        _dep(target="com.oldpkg.Utils.helper", rebuilt="com.newpkg.Utils.helper"),
    )
    err = gate4_dependency.check(src, deps)
    assert err is None


def test_no_deps_no_extra_returns_none() -> None:
    src = "class X { void f() {} }"
    err = gate4_dependency.check(src, ())
    assert err is None
