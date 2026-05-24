from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from omnix.cli import main


def test_status_reports_indexed_commit_when_db_present(
    git_repo: Path,
    make_graph_db,
    git_head,
    monkeypatch,
) -> None:
    head = git_head(git_repo)
    db = make_graph_db(git_repo, head)
    monkeypatch.chdir(git_repo)

    result = CliRunner().invoke(main, ["status", "--db", str(db)])

    assert result.exit_code == 0, result.output
    assert head[:7] in result.output


def test_status_reports_current_commit_via_git(
    git_repo: Path,
    make_graph_db,
    git_head,
    monkeypatch,
) -> None:
    head = git_head(git_repo)
    db = make_graph_db(git_repo, head)
    monkeypatch.chdir(git_repo)

    result = CliRunner().invoke(main, ["status", "--db", str(db), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["current_commit"] == head


def test_status_reports_node_and_edge_counts(
    git_repo: Path,
    make_graph_db,
    git_head,
    monkeypatch,
) -> None:
    db = make_graph_db(git_repo, git_head(git_repo))
    monkeypatch.chdir(git_repo)

    result = CliRunner().invoke(main, ["status", "--db", str(db), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["node_count"] == 5
    assert payload["edge_count"] == 4


def test_status_reports_stale_when_indexed_commit_differs_from_current(
    git_repo: Path,
    make_graph_db,
    monkeypatch,
) -> None:
    db = make_graph_db(git_repo, "0" * 40)
    monkeypatch.chdir(git_repo)

    result = CliRunner().invoke(main, ["status", "--db", str(db), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "stale"


def test_status_reports_up_to_date_when_commits_match(
    git_repo: Path,
    make_graph_db,
    git_head,
    monkeypatch,
) -> None:
    head = git_head(git_repo)
    db = make_graph_db(git_repo, head)
    monkeypatch.chdir(git_repo)

    result = CliRunner().invoke(main, ["status", "--db", str(db), "--json"])

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "up-to-date"


def test_status_missing_db_reports_no_index_exit_code_2(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)

    result = CliRunner().invoke(main, ["status", "--db", str(tmp_path / "missing.db")])

    assert result.exit_code == 2
    assert "no index" in result.output.lower()
