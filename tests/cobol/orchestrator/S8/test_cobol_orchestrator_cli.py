from __future__ import annotations

from click.testing import CliRunner


def test_cli_help_surfaces_new_orchestrator_commands() -> None:
    from omnix.cli import main

    runner = CliRunner()
    for command in ("modernize", "decide", "audit-export", "runs"):
        result = runner.invoke(main, ["cobol", command, "--help"])
        assert result.exit_code == 0, result.output


def test_cli_runs_list_empty(tmp_path) -> None:
    from omnix.cli import main

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(main, ["cobol", "runs"])

    assert result.exit_code == 0
    assert "No COBOL orchestrator runs" in result.output

