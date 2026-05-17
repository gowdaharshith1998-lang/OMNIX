"""Unit tests for function signature extraction (ast)."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from omnix.verify import signature

FIX = Path(__file__).resolve().parent / "fixtures"


def test_typed_tuples() -> None:
    res = signature.extract_signatures(FIX / "sample_typed.py", function_name="add")
    assert len(res) == 1
    fn = res[0]
    assert fn["name"] == "add"
    assert fn["params"] == [("a", "int"), ("b", "int")]
    assert fn["return_hint"] == "int"
    assert fn["is_async"] is False
    assert "lineno" in fn


def test_list_and_tuple_hints() -> None:
    res = signature.extract_signatures(
        FIX / "sample_typed.py", function_name="join_words"
    )
    assert "List" in res[0]["params"][0][1] or "list" in (res[0]["params"][0][1] or "")


def test_untyped_none_hints() -> None:
    res = signature.extract_signatures(FIX / "sample_untyped.py", function_name="merge")
    pnames = [p[0] for p in res[0]["params"]]
    hints = [p[1] for p in res[0]["params"]]
    assert pnames == ["a", "b", "c"]
    assert all(h is None for h in hints)
    # default recorded but not used for bounds
    assert "c" in (res[0].get("defaults", {}) or res[0].get("param_defaults", {}))


def test_varargs_kwarags_skipped(
    caplog: pytest.LogCaptureFixture, tmp_path: Path
) -> None:
    p = tmp_path / "v.py"
    p.write_text(
        "def wide(a: int, *args, **kwargs) -> int:\n    return a\n", encoding="utf-8"
    )
    with caplog.at_level(logging.WARNING, logger="verify.signature"):
        out = signature.extract_signatures(p, function_name="wide")
    assert out[0]["name"] == "wide"
    names = [n for n, _ in out[0]["params"]]
    assert "a" in names
    assert "args" not in names
    assert "kwargs" not in names


def test_async_def(tmp_path: Path) -> None:
    p = tmp_path / "a.py"
    p.write_text(
        "async def af(x: str) -> bool:\n" "    return bool(x)\n", encoding="utf-8"
    )
    res = signature.extract_signatures(p, function_name="af")
    assert res[0]["is_async"] is True
    assert res[0]["params"] == [("x", "str")]
