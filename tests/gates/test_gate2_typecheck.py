"""Tests for gate2_typecheck — heuristic import sanity + xfail real-parser cases."""

from __future__ import annotations

import pytest

from omnix.gates import gate2_typecheck

# ----- Heuristic path -------------------------------------------------------


def test_no_imports_returns_none() -> None:
    src = "class Foo { void x() {} }"
    err = gate2_typecheck.check(src)
    assert err is None


def test_well_formed_imports_return_none() -> None:
    src = """
    import java.util.List;
    import java.util.Map;
    import static java.lang.Math.PI;

    class Foo {}
    """
    err = gate2_typecheck.check(src)
    assert err is None


def test_on_demand_import_returns_none() -> None:
    src = """
    import java.util.*;
    class Foo {}
    """
    err = gate2_typecheck.check(src)
    assert err is None


def test_malformed_import_with_leading_digit_returns_gate_error() -> None:
    # FQN starting with a digit isn't a valid Java identifier.
    src = "import 9broken.Foo;\nclass Bar {}\n"
    err = gate2_typecheck.check(src)
    assert err is not None
    assert err.gate_number == 2
    assert err.gate_name == "typecheck"
    assert err.details["unresolvable_type"] == "9broken.Foo"
    assert err.details["context"] == "import"
    assert err.details["source_line"] == 1


def test_malformed_import_with_dash_returns_gate_error() -> None:
    src = "\nimport com.foo-bar.Baz;\nclass X {}\n"
    err = gate2_typecheck.check(src)
    assert err is not None
    assert err.details["unresolvable_type"] == "com.foo-bar.Baz"
    assert err.details["source_line"] == 2


def test_returns_gate_error_dataclass_with_required_keys() -> None:
    err = gate2_typecheck.check("import 1bad;\n")
    assert err is not None
    assert set(err.details.keys()) >= {"unresolvable_type", "source_line", "context"}


# ----- Real-parser xfail cases ---------------------------------------------


@pytest.mark.xfail(strict=True, reason="JVM JAR not vendored")
def test_real_parser_reports_unresolvable_type_in_method_body() -> None:
    src = """
    class Foo {
        void x() {
            UnknownType u = new UnknownType();
        }
    }
    """
    err = gate2_typecheck.check(src)
    assert err is not None
    assert err.details["unresolvable_type"] == "UnknownType"


@pytest.mark.xfail(strict=True, reason="JVM JAR not vendored")
def test_real_parser_resolves_classpath_imports() -> None:
    # Heuristic only checks import FQN syntax; it cannot verify the referenced
    # body uses ArrayList correctly. This test asserts the FULL resolution
    # surface — including detecting `MissingClass` used in the body — which
    # only the real symbol-solver can deliver. Until then, heuristic passes
    # (no malformed imports) so the assertion-with-MissingClass-in-body XFAILs.
    src = """
    import java.util.ArrayList;
    class Foo {
        ArrayList<String> a = new ArrayList<>();
        MissingClass m = new MissingClass();
    }
    """
    err = gate2_typecheck.check(src)
    assert err is not None
    assert err.details["unresolvable_type"] == "MissingClass"
