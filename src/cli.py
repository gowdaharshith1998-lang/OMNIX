# Compliance: P21

"""OMNIX CLI: `omnix axiom`, `omnix grammar`, `omnix analyze` (Studio), and related commands."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from axiom.cli import axiom_group
from parser.cli import grammar_group


@click.group()
@click.version_option(version="0.1.0", prog_name="omnix")
def main() -> None:
    """OMNIX — code intelligence and AXIOM provenance."""


def _ensure_repo_root_on_syspath() -> None:
    """`studio.server` imports `src.*`; repo root must precede those imports."""
    repo = str(Path(__file__).resolve().parents[1])
    if repo not in sys.path:
        sys.path.insert(0, repo)


@click.command(context_settings={"help_option_names": ["-h", "--help"]})
@click.argument(
    "path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=str),
    default=".",
)
@click.option("--port", type=int, default=7777, help="Web UI port")
@click.option(
    "--no-open",
    "--no-browser",
    is_flag=True,
    default=False,
    help="Do not launch a browser (still serves on --port)",
)
def analyze(path: str, port: int, no_open: bool) -> None:
    """Analyze a codebase and open OMNIX Studio (FastAPI on --port)."""
    import threading
    import webbrowser

    target = str(Path(path).resolve())
    _ensure_repo_root_on_syspath()
    from src.studio.server import run as studio_run

    url = f"http://127.0.0.1:{port}/"
    print(f"🌐 OMNIX running at {url}")
    if not no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        studio_run(project_path=target, port=port)
    except KeyboardInterrupt:
        print("\n✨ OMNIX stopped")


main.add_command(axiom_group, name="axiom")
main.add_command(grammar_group, name="grammar")
main.add_command(analyze)


if __name__ == "__main__":
    main()
