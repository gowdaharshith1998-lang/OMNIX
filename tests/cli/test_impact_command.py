from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from omnix.cli import main


def test_impact_upstream_returns_callers_at_depth_1(
    git_repo: Path,
    make_graph_db,
    git_head,
    monkeypatch,
) -> None:
    db = make_graph_db(git_repo, git_head(git_repo))
    monkeypatch.chdir(git_repo)

    result = CliRunner().invoke(
        main,
        ["impact", "target", "--db", str(db), "--direction", "upstream", "--depth", "1"],
    )

    assert result.exit_code == 0, result.output
    assert "Depth 1" in result.output
    assert "src/caller.py::caller" in result.output
    assert "src/caller.py::caller2" not in result.output


def test_impact_downstream_returns_callees_at_depth_1(
    git_repo: Path,
    make_graph_db,
    git_head,
    monkeypatch,
) -> None:
    db = make_graph_db(git_repo, git_head(git_repo))
    monkeypatch.chdir(git_repo)

    result = CliRunner().invoke(
        main,
        ["impact", "target", "--db", str(db), "--direction", "downstream", "--depth", "1"],
    )

    assert result.exit_code == 0, result.output
    assert "src/app.py::callee" in result.output


def test_impact_depth_2_returns_transitive(
    git_repo: Path,
    make_graph_db,
    git_head,
    monkeypatch,
) -> None:
    db = make_graph_db(git_repo, git_head(git_repo))
    monkeypatch.chdir(git_repo)

    result = CliRunner().invoke(
        main,
        ["impact", "target", "--db", str(db), "--direction", "upstream", "--depth", "2"],
    )

    assert result.exit_code == 0, result.output
    assert "Depth 2" in result.output
    assert "src/caller.py::caller2" in result.output


def test_impact_include_tests_flag_includes_test_files(
    git_repo: Path,
    make_graph_db,
    git_head,
    monkeypatch,
) -> None:
    db = make_graph_db(git_repo, git_head(git_repo))
    monkeypatch.chdir(git_repo)

    without_tests = CliRunner().invoke(
        main,
        ["impact", "target", "--db", str(db), "--direction", "upstream", "--depth", "1"],
    )
    with_tests = CliRunner().invoke(
        main,
        [
            "impact",
            "target",
            "--db",
            str(db),
            "--direction",
            "upstream",
            "--depth",
            "1",
            "--include-tests",
        ],
    )

    assert without_tests.exit_code == 0, without_tests.output
    assert with_tests.exit_code == 0, with_tests.output
    assert "tests/test_app.py::test_target" not in without_tests.output
    assert "tests/test_app.py::test_target" in with_tests.output


def test_impact_unknown_symbol_exits_with_error_code_2(
    git_repo: Path,
    make_graph_db,
    git_head,
    monkeypatch,
) -> None:
    db = make_graph_db(git_repo, git_head(git_repo))
    monkeypatch.chdir(git_repo)

    result = CliRunner().invoke(main, ["impact", "missing_symbol", "--db", str(db)])

    assert result.exit_code == 2
    assert "unknown symbol" in result.output.lower()


def test_impact_emits_json_when_json_flag_set(
    git_repo: Path,
    make_graph_db,
    git_head,
    monkeypatch,
) -> None:
    db = make_graph_db(git_repo, git_head(git_repo))
    monkeypatch.chdir(git_repo)

    result = CliRunner().invoke(
        main,
        ["impact", "target", "--db", str(db), "--direction", "both", "--depth", "1", "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["symbol"] == "target"
    assert payload["direction"] == "both"
    assert {node["id"] for node in payload["nodes"]} >= {
        "src/caller.py::caller",
        "src/app.py::callee",
    }
