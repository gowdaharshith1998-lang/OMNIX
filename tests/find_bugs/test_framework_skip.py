"""Framework / async / pytest decorators are skipped before PBT."""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

pytest.importorskip("hypothesis", reason="hypothesis required")

from find_bugs import runner


def _run_find(
    root: Path,
    tmp_path: Path,
    empty_graph_db_path: str,
    monkeypatch: pytest.MonkeyPatch,
) -> dict:
    monkeypatch.setenv("HOME", str(tmp_path))
    (tmp_path / ".omnix" / "receipts").mkdir(parents=True, exist_ok=True)
    ex, _out, detail = runner.run_find_bugs(
        str(root),
        examples=10,
        top=5,
        json_mode=True,
        no_bundle=True,
        include_private=False,
        max_file_size=1_000_000,
        graph_db=empty_graph_db_path,
    )
    assert ex in (0, 1)
    assert detail is not None
    return detail


def test_skip_click_command(
    tmp_path: Path, empty_graph_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "cli.py"
    f.write_text(
        textwrap.dedent(
            """
        import click

        @click.command()
        @click.argument('path')
        def cli(path):
            pass
    """
        ),
        encoding="utf-8",
    )
    b = _run_find(tmp_path, tmp_path, empty_graph_db_path, monkeypatch)
    sm = b.get("skipped_main") or []
    assert any(s.get("function") == "cli" for s in sm if isinstance(s, dict))
    for s in sm:
        if s.get("function") == "cli" and (r := s.get("reason", "")):
            assert "framework_decorator" in r or "click" in r.lower()
            break
    else:
        pytest.fail("expected cli in skipped_main with a framework reason")


def test_skip_fastapi_route(
    tmp_path: Path, empty_graph_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "api.py"
    f.write_text(
        textwrap.dedent(
            """
        from fastapi import FastAPI
        app = FastAPI()

        @app.get("/health")
        def health():
            return {"ok": True}
    """
        ),
        encoding="utf-8",
    )
    b = _run_find(tmp_path, tmp_path, empty_graph_db_path, monkeypatch)
    sm = b.get("skipped_main") or []
    assert any(s.get("function") == "health" for s in sm if isinstance(s, dict))


def test_skip_async_top_level(
    tmp_path: Path, empty_graph_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "async_code.py"
    f.write_text(
        textwrap.dedent(
            """
        async def fetch_data(url):
            return None
    """
        ),
        encoding="utf-8",
    )
    b = _run_find(tmp_path, tmp_path, empty_graph_db_path, monkeypatch)
    sm = b.get("skipped_main") or []
    assert any(
        s.get("function") == "fetch_data" and s.get("reason") == "async_top_level"
        for s in sm
        if isinstance(s, dict)
    )


def test_allow_safe_decorators(
    tmp_path: Path, empty_graph_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "safe.py"
    f.write_text(
        textwrap.dedent(
            """
        from functools import lru_cache

        @lru_cache(maxsize=128)
        def add(a: int, b: int) -> int:
            return a + b
    """
        ),
        encoding="utf-8",
    )
    b = _run_find(tmp_path, tmp_path, empty_graph_db_path, monkeypatch)
    skipped_names = {s.get("function") for s in b.get("skipped_main") or [] if isinstance(s, dict)}
    assert "add" not in skipped_names
    total = (b.get("summary") or {}).get("total_examples_run", 0) or 0
    assert total >= 10


def test_skip_typer_command(
    tmp_path: Path, empty_graph_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "typer_app.py"
    f.write_text(
        textwrap.dedent(
            """
        import typer
        app = typer.Typer()

        @app.command()
        def hello(name: str):
            typer.echo("hello " + str(name))
    """
        ),
        encoding="utf-8",
    )
    b = _run_find(tmp_path, tmp_path, empty_graph_db_path, monkeypatch)
    sm = b.get("skipped_main") or []
    assert any(s.get("function") == "hello" for s in sm if isinstance(s, dict))


def test_skip_pytest_fixture(
    tmp_path: Path, empty_graph_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "conftest.py"
    f.write_text(
        textwrap.dedent(
            """
        import pytest

        @pytest.fixture
        def db():
            return {}
    """
        ),
        encoding="utf-8",
    )
    b = _run_find(tmp_path, tmp_path, empty_graph_db_path, monkeypatch)
    sm = b.get("skipped_main") or []
    assert any(s.get("function") == "db" for s in sm if isinstance(s, dict))


def test_multiple_decorators_safety_net(
    tmp_path: Path, empty_graph_db_path: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    f = tmp_path / "weird.py"
    f.write_text(
        textwrap.dedent(
            """
        def deco1(f):
            return f
        def deco2(f):
            return f

        @deco1
        @deco2
        def stacked(x):
            return x
    """
        ),
        encoding="utf-8",
    )
    b = _run_find(tmp_path, tmp_path, empty_graph_db_path, monkeypatch)
    skipped = [s for s in b.get("skipped_main") or [] if s.get("function") == "stacked"]
    assert len(skipped) == 1
    assert "multiple" in (skipped[0].get("reason") or "").lower()
