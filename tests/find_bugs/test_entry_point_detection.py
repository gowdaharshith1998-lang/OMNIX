"""Entry point heuristics (``__name__``, decorators, argparse)."""

from __future__ import annotations

from pathlib import Path

import pytest

from omnix.find_bugs.entry_points import detect_entry_points


def test_name_main(main_py: Path, sample_root: Path) -> None:
    ep = detect_entry_points(main_py, sample_root)
    # main.py calls main() under __name__ guard
    rel = "main.py"
    assert f"{rel}:main" in ep or any("main" in e for e in ep)


def test_flask_and_click(tmp_path: Path) -> None:
    p = tmp_path / "api.py"
    p.write_text(
        """
from flask import Flask
app = Flask(__name__)
@app.route("/x")
def hi():
    pass
import click
@click.command()
def cli_e():
    pass
""",
        encoding="utf-8",
    )
    ep = detect_entry_points(p, tmp_path)
    l = " ".join(ep)
    assert "hi" in l
    assert "cli_e" in l


def test_argparse_set_defaults(tmp_path: Path) -> None:
    p = tmp_path / "c.py"
    p.write_text(
        """
import argparse
def build_cmd(x):
    pass
p = argparse.ArgumentParser()
sp = p.add_subparsers()
b = sp.add_parser("b")
b.set_defaults(func=build_cmd)
""",
        encoding="utf-8",
    )
    assert any("build_cmd" in s for s in detect_entry_points(p, tmp_path))


def test_no_entry_in_empty_file(tmp_path: Path) -> None:
    p = tmp_path / "e.py"
    p.write_text("X = 1\n", encoding="utf-8")
    assert detect_entry_points(p, tmp_path) == []


@pytest.fixture
def sample_root() -> Path:
    return Path(__file__).parent / "fixtures" / "sample_codebase"


@pytest.fixture
def main_py(sample_root: Path) -> Path:
    return sample_root / "main.py"
