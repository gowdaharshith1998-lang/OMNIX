"""ITER 5a: walker + grammar_detect dispatch."""

from __future__ import annotations

import pytest

from find_bugs import walker
from src.parser.grammar_detect import detect_for_path


def test_walker_dispatches_python_to_dedicated_parser(tmp_path) -> None:
    (tmp_path / "a.pyi").write_text("def f() -> int: ...\n", encoding="utf-8")
    assert (tmp_path / "a.pyi") in set(walker.iter_dispatch_paths(tmp_path))
    d = detect_for_path(tmp_path / "a.pyi")
    assert d.grammar_name == "python"
    if d.language is not None:
        assert d.skip_reason is None
    else:
        pytest.skip("tree_sitter_python not installed; grammar wheel missing is ok")


def test_walker_dispatches_unknown_ext_to_universal_or_skips(tmp_path) -> None:
    root = tmp_path / "t"
    root.mkdir()
    (root / "weird.xyz999").write_text("hello", encoding="utf-8")
    p = list(walker.iter_dispatch_paths(root, max_size=1_000_000))
    assert (root / "weird.xyz999") in p
    d = detect_for_path(root / "weird.xyz999")
    assert d.skip_reason == "unknown_extension"
