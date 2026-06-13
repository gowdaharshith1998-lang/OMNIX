"""Tests for the D3 transformer DSL + RestrictedPython sandbox.

THE SECURITY KERNEL. A regression here means LLM-emitted code could potentially
escape the sandbox and execute on the migration host. Treat as security-critical.
"""

from __future__ import annotations

import pytest

from omnix.dm.d3_transformation_synthesis.transformer_dsl import (
    ALLOWED_AST_NODES,
    ALLOWED_CALLS,
    ALLOWED_MODULE_ATTRS,
    _SecurityViolationError,
    compile_safe,
    validate_ast,
)

# ---------------- happy paths ----------------


def test_simple_upper_validates():
    validate_ast("def transform(v): return v.upper()")


def test_lambda_arithmetic_validates():
    validate_ast("def transform(v): return int(v) * 2")


def test_datetime_combine_validates():
    src = (
        "def transform(v):\n"
        "    if v is None: return None\n"
        "    return datetime.datetime.combine(v, datetime.time.min, "
        "tzinfo=datetime.timezone.utc)\n"
    )
    validate_ast(src)
    compile_safe(src)


def test_decimal_quantize_validates():
    src = (
        "def transform(v):\n"
        "    if v is None: return None\n"
        '    d = decimal.Decimal(str(v))\n'
        '    q = decimal.Decimal("1E-2")\n'
        "    return d.quantize(q, rounding=decimal.ROUND_HALF_UP)\n"
    )
    validate_ast(src)
    compile_safe(src)


def test_re_sub_validates():
    src = 'def transform(v):\n    return re.sub(r"\\s+", " ", v)'
    validate_ast(src)
    compile_safe(src)


# ---------------- known sandbox escapes ----------------


def _expect_violation(source: str) -> _SecurityViolationError:
    with pytest.raises(_SecurityViolationError) as exc:
        validate_ast(source)
        compile_safe(source)
    return exc.value


def test_import_statement_blocked():
    v = _expect_violation("def transform(v):\n    import os\n    return os")
    assert "Import" in v.violation.node_type


def test_dunder_import_call_blocked():
    src = 'def transform(v): return __import__("os").system("id")'
    _expect_violation(src)


def test_class_bases_subclasses_chain_blocked():
    src = "def transform(v): return ().__class__.__bases__[0].__subclasses__()"
    v = _expect_violation(src)
    assert "dunder" in v.violation.reason.lower() or v.violation.node_type.startswith(
        "Attribute"
    )


def test_open_call_blocked():
    src = 'def transform(v): return open("/etc/passwd").read()'
    _expect_violation(src)


def test_mro_traversal_blocked():
    src = "def transform(v): return (0).__class__.__mro__[1]"
    _expect_violation(src)


def test_lambda_globals_blocked():
    src = "def transform(v): return (lambda: None).__globals__"
    _expect_violation(src)


def test_subclasses_subprocess_chain_blocked():
    src = (
        "def transform(v): "
        "return ''.__class__.__bases__[0].__subclasses__()[40]"
        "('cat /etc/passwd', shell=True)"
    )
    _expect_violation(src)


def test_dunder_dict_blocked():
    src = "def transform(v): return datetime.__dict__"
    _expect_violation(src)


def test_eval_through_getattr_blocked():
    src = 'def transform(v): return getattr(v, "eval")'
    # getattr isn't in ALLOWED_CALLS so the Call check rejects it.
    _expect_violation(src)


def test_classdef_blocked():
    src = "def transform(v):\n    class X: pass\n    return X"
    v = _expect_violation(src)
    assert "ClassDef" in v.violation.node_type


def test_while_loop_blocked():
    src = "def transform(v):\n    while True:\n        return 1"
    v = _expect_violation(src)
    assert "While" in v.violation.node_type


def test_for_loop_blocked():
    # for-loops are out of the allowlist; transformer must use list/dict comprehensions.
    src = "def transform(v):\n    out = []\n    for x in v:\n        out.append(x)\n    return out"
    v = _expect_violation(src)
    assert "For" in v.violation.node_type


def test_try_block_blocked():
    src = "def transform(v):\n    try:\n        return int(v)\n    except: return None"
    v = _expect_violation(src)
    assert "Try" in v.violation.node_type


def test_yield_blocked():
    src = "def transform(v):\n    yield v"
    v = _expect_violation(src)
    assert "Yield" in v.violation.node_type


def test_with_blocked():
    src = "def transform(v):\n    with v as x:\n        return x"
    v = _expect_violation(src)
    assert "With" in v.violation.node_type


def test_async_blocked():
    src = "async def transform(v):\n    return v"
    v = _expect_violation(src)
    assert "Async" in v.violation.node_type


def test_format_string_class_blocked():
    # f-string evaluation isn't allowed to chain into dunders.
    src = 'def transform(v): return f"{v.__class__}"'
    _expect_violation(src)


def test_co_consts_decompile_blocked():
    src = "def transform(v): return (lambda: 0).__code__"
    _expect_violation(src)


# ---------------- allowlist invariants ----------------


def test_allowlist_is_frozen():
    assert isinstance(ALLOWED_AST_NODES, frozenset)
    assert isinstance(ALLOWED_CALLS, frozenset)
    assert isinstance(ALLOWED_MODULE_ATTRS, frozenset)
    # adding a new dangerous node type must not silently slip through:
    assert "Import" not in ALLOWED_AST_NODES
    assert "ImportFrom" not in ALLOWED_AST_NODES
    assert "ClassDef" not in ALLOWED_AST_NODES
    assert "Try" not in ALLOWED_AST_NODES
    assert "open" not in ALLOWED_CALLS
    assert "eval" not in ALLOWED_CALLS
    assert "exec" not in ALLOWED_CALLS
    assert "__import__" not in ALLOWED_CALLS
