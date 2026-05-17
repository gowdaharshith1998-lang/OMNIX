"""Unit tests for package-aware module loading in the verify runner."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from omnix.verify.runner import _load_target_module

REPO = Path(__file__).resolve().parents[2]
FIX = Path(__file__).parent / "fixtures"
FLAT = FIX / "sample_typed.py"
PKG = FIX / "pkg_with_relimport" / "target.py"
BROKEN = FIX / "syntaxerr_target.py"
ENCODING = REPO / "src" / "omnix" / "receipts" / "encoding.py"

pytest.importorskip("hypothesis", reason="hypothesis required")


def _unload_new_modules(before: set[str]) -> None:
    for k in set(sys.modules) - before:
        del sys.modules[k]


def test_load_flat_file_module() -> None:
    path_before = sys.path.copy()
    pre_mod = set(sys.modules)
    m = _load_target_module(FLAT)
    try:
        assert m.__name__ == "sample_typed"
        assert hasattr(m, "add")
        assert callable(m.add)  # type: ignore[union-attr, misc]
    finally:
        _unload_new_modules(pre_mod)
    assert sys.path == path_before


def test_load_package_module_with_relative_import() -> None:
    path_before = sys.path.copy()
    pre_mod = set(sys.modules)
    m = _load_target_module(PKG)
    try:
        assert m.__name__ == "pkg_with_relimport.target"
        assert hasattr(m, "use_helper")
        assert m.use_helper(5) == 6  # type: ignore[union-attr, misc, operator]
    finally:
        _unload_new_modules(pre_mod)
    assert sys.path == path_before


def test_load_package_module_smoke_real_axiom() -> None:
    if not ENCODING.is_file():
        pytest.skip("src/omnix/receipts/encoding.py not in tree")
    path_before = sys.path.copy()
    pre_mod = set(sys.modules)
    m = _load_target_module(ENCODING)
    try:
        assert hasattr(m, "bitlen_u64")
        assert callable(m.bitlen_u64)  # type: ignore[union-attr, misc]
    finally:
        _unload_new_modules(pre_mod)
    assert sys.path == path_before


def test_loader_failure_propagates() -> None:
    with pytest.raises((SyntaxError, ImportError, ModuleNotFoundError)):
        _load_target_module(BROKEN)
