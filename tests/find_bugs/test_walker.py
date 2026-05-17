"""File discovery: ignores, .gitignore, size, and parseability."""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from omnix.find_bugs import walker


def test_finds_expected_py_in_fixture(tmp_path: Path) -> None:
    a = tmp_path / "a.py"
    a.write_text("X = 1\n", encoding="utf-8")
    sub = tmp_path / "pkg"
    sub.mkdir()
    (sub / "b.py").write_text("Y=2\n", encoding="utf-8")
    out = set(
        walker.walk_python_files(tmp_path, require_parseable=True)
    )
    assert a in out
    assert (sub / "b.py") in out


def test_skips_venv_and_pycache(tmp_path: Path) -> None:
    (tmp_path / "good.py").write_text("1\n", encoding="utf-8")
    (tmp_path / "venv" / "site.py").parent.mkdir(parents=True, exist_ok=True)
    (tmp_path / "venv" / "site.py").write_text("x\n", encoding="utf-8")
    c = tmp_path / "__pycache__" / "x.cpython-311.pyc"
    c.parent.mkdir(parents=True, exist_ok=True)
    c.write_text("bad", encoding="utf-8")
    out = {
        p.resolve()
        for p in walker.walk_python_files(tmp_path, require_parseable=True)
    }
    assert (tmp_path / "good.py").resolve() in out
    assert not any("venv" in p.parts for p in out)


def test_gitignore_prefix(tmp_path: Path) -> None:
    (tmp_path / ".gitignore").write_text("ignore_me/\n", encoding="utf-8")
    (tmp_path / "keep.py").write_text("1\n", encoding="utf-8")
    ign = tmp_path / "ignore_me" / "bad.py"
    ign.parent.mkdir(parents=True, exist_ok=True)
    ign.write_text("1\n", encoding="utf-8")
    out = list(walker.walk_python_files(tmp_path, require_parseable=True))
    assert (tmp_path / "keep.py") in out
    assert not any("ignore_me" in str(p) for p in out)


def test_skips_known_pathological_relative_paths(tmp_path: Path) -> None:
    skipped = tmp_path / "src" / "omnix" / "axiom" / "ntt.py"
    skipped.parent.mkdir(parents=True)
    skipped.write_text("def add_ntt(a, b):\n    return a + b\n", encoding="utf-8")
    same_basename = tmp_path / "other" / "ntt.py"
    same_basename.parent.mkdir()
    same_basename.write_text("def safe(a, b):\n    return a + b\n", encoding="utf-8")

    out = set(walker.walk_python_files(tmp_path, require_parseable=True))

    assert skipped not in out
    assert same_basename in out


def test_skips_huge_file(tmp_path: Path) -> None:
    p = tmp_path / "huge.py"
    p.write_bytes(b"#" * 2_000_000)
    n = list(
        walker.walk_python_files(
            tmp_path, max_size=1_000_000, require_parseable=True
        )
    )
    assert n == []


def test_unparseable_emits_warning(caplog: pytest.LogCaptureFixture, tmp_path: Path) -> None:
    p = tmp_path / "x.py"
    p.write_text("def x((a):\n  pass\n", encoding="utf-8")
    with caplog.at_level(logging.WARNING, logger="find_bugs.walker"):
        n = list(walker.walk_python_files(tmp_path, require_parseable=True))
    assert n == []
    assert "unparseable" in caplog.text
