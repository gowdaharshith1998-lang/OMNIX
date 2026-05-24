from __future__ import annotations

import json
from pathlib import Path

from click.testing import CliRunner

from omnix.cli import main


def test_detect_changes_staged_returns_only_git_staged_files(
    git_repo: Path,
    make_graph_db,
    git_head,
    git_cmd,
    monkeypatch,
) -> None:
    db = make_graph_db(git_repo, git_head(git_repo))
    (git_repo / "src" / "app.py").write_text("def target():\n    return 2\n", encoding="utf-8")
    (git_repo / "src" / "caller.py").write_text("def caller():\n    return 3\n", encoding="utf-8")
    git_cmd(git_repo, "add", "src/app.py")
    monkeypatch.chdir(git_repo)

    result = CliRunner().invoke(
        main,
        ["detect-changes", "--scope", "staged", "--db", str(db), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    files = {entry["file"] for entry in payload["files"]}
    assert "src/app.py" in files
    assert "src/caller.py" not in files


def test_detect_changes_worktree_returns_dirty_files_including_unstaged(
    git_repo: Path,
    make_graph_db,
    git_head,
    git_cmd,
    monkeypatch,
) -> None:
    db = make_graph_db(git_repo, git_head(git_repo))
    (git_repo / "src" / "app.py").write_text("def target():\n    return 2\n", encoding="utf-8")
    (git_repo / "src" / "caller.py").write_text("def caller():\n    return 3\n", encoding="utf-8")
    git_cmd(git_repo, "add", "src/app.py")
    monkeypatch.chdir(git_repo)

    result = CliRunner().invoke(
        main,
        ["detect-changes", "--scope", "worktree", "--db", str(db), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    files = {entry["file"] for entry in payload["files"]}
    assert {"src/app.py", "src/caller.py"} <= files


def test_detect_changes_all_returns_full_drift_from_indexed_commit(
    git_repo: Path,
    make_graph_db,
    git_head,
    git_cmd,
    monkeypatch,
) -> None:
    indexed_commit = git_head(git_repo)
    db = make_graph_db(git_repo, indexed_commit)
    (git_repo / "src" / "app.py").write_text("def target():\n    return 4\n", encoding="utf-8")
    git_cmd(git_repo, "add", "src/app.py")
    git_cmd(git_repo, "commit", "-m", "change app")
    monkeypatch.chdir(git_repo)

    result = CliRunner().invoke(
        main,
        [
            "detect-changes",
            "--scope",
            "all",
            "--since-commit",
            indexed_commit,
            "--db",
            str(db),
            "--json",
        ],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "src/app.py" in {entry["file"] for entry in payload["files"]}


def test_detect_changes_emits_symbol_level_diff_when_index_present(
    git_repo: Path,
    make_graph_db,
    git_head,
    git_cmd,
    monkeypatch,
) -> None:
    db = make_graph_db(git_repo, git_head(git_repo))
    (git_repo / "src" / "app.py").write_text("def target():\n    return 2\n", encoding="utf-8")
    git_cmd(git_repo, "add", "src/app.py")
    monkeypatch.chdir(git_repo)

    result = CliRunner().invoke(
        main,
        ["detect-changes", "--scope", "staged", "--db", str(db), "--json"],
    )

    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    app = next(entry for entry in payload["files"] if entry["file"] == "src/app.py")
    assert app["nodes"] == 2
    assert app["edges"] == 1
