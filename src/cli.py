# Compliance: P21

"""OMNIX top-level click CLI (pip entry point)."""

from __future__ import annotations

# --- Pip-entry sys.path bootstrap ----------------------------------------
# When `omnix` is invoked via the pip-installed entry script, sys.path
# contains the contents of src/ (so `cli`, `parser`, `axiom`, etc. are
# top-level packages) but NOT the repo root. As a result, the many
# `from src.X` imports throughout the codebase fail because `src` is not
# resolvable as a package.
#
# We fix this once at module load time by inserting the repo root onto
# sys.path. Idempotent — no-op when already present (pytest, python omnix.py).
# This must run BEFORE any imports of subcommand modules below.
import sys
from pathlib import Path

_repo_root = Path(__file__).resolve().parent.parent
if str(_repo_root) not in sys.path:
    sys.path.insert(0, str(_repo_root))
# -------------------------------------------------------------------------

import click

try:
    from omnix_version import __version__ as _OMNIX_VERSION  # pip-entry (src on path)
except ImportError:
    from src.omnix_version import __version__ as _OMNIX_VERSION

from axiom.cli import axiom_group
from parser.cli import grammar_group


@click.group()
@click.version_option(version=_OMNIX_VERSION, prog_name="omnix")
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


@main.command(
    "find-bugs",
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
        "help_option_names": ["-h", "--help"],
    },
)
@click.pass_context
def find_bugs_cmd(ctx: click.Context) -> None:
    """Scan a codebase for bugs (with optional --emit-receipts)."""
    try:
        from find_bugs.cli import run as _fb_run
    except ImportError:
        from src.find_bugs.cli import run as _fb_run

    rc = _fb_run(argv=list(ctx.args))
    sys.exit(rc if isinstance(rc, int) else 0)


if __name__ == "__main__":
    main()
