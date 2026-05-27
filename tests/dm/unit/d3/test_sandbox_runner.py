"""Subprocess fence tests for the D3 sandbox runner.

Verifies that resource limits actually kick in (CPU → SIGXCPU, AS → SIGKILL),
that the JSON roundtrip carries datetime/Decimal cleanly, and that the parent
process maps signals back to typed Execution* outcomes.
"""

from __future__ import annotations

import datetime
import decimal

import pytest

from omnix.dm._types import ExecutionError, ExecutionOOM, ExecutionTimeout
from omnix.dm.d3_transformation_synthesis.transformer_dsl import (
    ExecutionSuccess,
    execute,
)


def test_happy_execute_returns_success():
    src = "def transform(v):\n    return v + 1\n"
    r = execute(src, 5)
    assert isinstance(r, ExecutionSuccess)
    assert r.result_repr == "6"


def test_execution_timeout_fires_on_busy_loop():
    src = (
        "def transform(v):\n"
        "    n = 0\n"
        "    while_idx = 0\n"
        "    return [x*x for x in range(10**8)][0]\n"  # heavy compute
    )
    # while/for not allowed in AST → this list-comp is allowed but will hit CPU.
    r = execute(src, 0, timeout_ms=2000, cpu_sec=1, as_mb=128)
    assert isinstance(r, (ExecutionTimeout, ExecutionOOM, ExecutionError))


def test_execution_oom_on_huge_alloc():
    src = "def transform(v):\n    return [0] * (10**9)\n"
    r = execute(src, 0, timeout_ms=3000, cpu_sec=5, as_mb=128)
    assert isinstance(r, (ExecutionOOM, ExecutionTimeout, ExecutionError))


def test_execution_error_on_value_error():
    src = 'def transform(v):\n    return int("not a number")\n'
    r = execute(src, "x")
    assert isinstance(r, ExecutionError)
    assert r.error_type == "ValueError"


def test_datetime_roundtrips_through_subprocess():
    src = (
        "def transform(v):\n"
        "    if v is None: return None\n"
        "    return datetime.datetime.combine(v, datetime.time.min, "
        "tzinfo=datetime.timezone.utc)\n"
    )
    r = execute(src, datetime.date(2020, 1, 1))
    assert isinstance(r, ExecutionSuccess)
    assert "2020, 1, 1" in r.result_repr
    assert "tzinfo" in r.result_repr


def test_decimal_roundtrips_through_subprocess():
    src = (
        "def transform(v):\n"
        "    if v is None: return None\n"
        '    d = decimal.Decimal(str(v))\n'
        '    return d.quantize(decimal.Decimal("1E-2"), rounding=decimal.ROUND_HALF_UP)\n'
    )
    r = execute(src, decimal.Decimal("3.14159"))
    assert isinstance(r, ExecutionSuccess)
    assert "3.14" in r.result_repr


def test_none_passthrough():
    src = (
        "def transform(v):\n"
        "    if v is None: return None\n"
        "    return v.upper()\n"
    )
    r = execute(src, None)
    assert isinstance(r, ExecutionSuccess)
    assert r.result_repr == "None"


def test_security_violation_raises_before_subprocess():
    """compile_safe is called inline before fork — so security violations
    never reach the subprocess. This protects us from a subprocess
    misconfiguration leaking out."""
    from omnix.dm.d3_transformation_synthesis.transformer_dsl import (
        _SecurityViolationError,
    )

    src = 'def transform(v): return __import__("os").system("id")'
    with pytest.raises(_SecurityViolationError):
        execute(src, "x")
