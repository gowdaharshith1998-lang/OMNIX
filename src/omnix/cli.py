# Compliance: P21

"""OMNIX top-level click CLI (pip entry point)."""

from __future__ import annotations

# --- Direct-file sys.path bootstrap ---------------------------------------
# Package entry points import `omnix.cli` through the installed distribution.
# Direct execution from the source tree needs `src/` on sys.path first so the
# `omnix` package wins over the root-level `omnix.py` wrapper.
import sys
from pathlib import Path

_src_root = Path(__file__).resolve().parents[1]
if str(_src_root) not in sys.path:
    sys.path.insert(0, str(_src_root))
# -------------------------------------------------------------------------

import click

from omnix.omnix_version import __version__ as _OMNIX_VERSION
from omnix.parser.cli import grammar_group
from omnix.receipts.cli import axiom_group


@click.group()
@click.version_option(version=_OMNIX_VERSION, prog_name="omnix")
def main() -> None:
    """OMNIX — knowledge intelligence and AXIOM provenance."""


def _ensure_src_on_syspath() -> None:
    """Keep direct source-tree execution importable."""
    src = str(Path(__file__).resolve().parents[1])
    if src not in sys.path:
        sys.path.insert(0, src)


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
    _ensure_src_on_syspath()
    from omnix.studio.server import run as studio_run

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
    from omnix.find_bugs.cli import run as _fb_run

    rc = _fb_run(argv=list(ctx.args))
    sys.exit(rc if isinstance(rc, int) else 0)


@main.command(
    "verify",
    context_settings={
        "ignore_unknown_options": True,
        "allow_extra_args": True,
        "help_option_names": ["-h", "--help"],
    },
)
@click.pass_context
def verify_cmd(ctx: click.Context) -> None:
    """Property-based test / verify a Python function."""
    from omnix.verify import cli as verify_cli

    args = verify_cli._build_parser().parse_args(list(ctx.args))
    rc = int(verify_cli.run(args))
    sys.exit(0 if rc == 0 else 1 if rc == 1 else 2)


if __name__ == "__main__":
    main()
