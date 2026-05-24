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

from omnix.cli_cobol import cobol_group
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
    from omnix.self_host_cli import emit_analyze_receipt, run_analyze_ingest
    from omnix.studio.server import run as studio_run

    db_path, wall_clock_seconds = run_analyze_ingest(Path(target))
    receipt = emit_analyze_receipt(Path(target), db_path, wall_clock_seconds)
    if receipt.signed:
        click.echo(f"Signed receipt: {receipt.receipt_path}")
        click.echo(
            f"Verify: omnix axiom verify {receipt.receipt_path} "
            f"{receipt.sig_path} --pubkey ~/.omnix/keys/public.pem"
        )
    else:
        click.echo(f"Receipt: {receipt.receipt_path}")

    url = f"http://127.0.0.1:{port}/"
    print(f"🌐 OMNIX running at {url}")
    if not no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()
    try:
        studio_run(project_path=target, port=port)
    except KeyboardInterrupt:
        print("\n✨ OMNIX stopped")


@click.command("rebuild", context_settings={"help_option_names": ["-h", "--help"]})
@click.argument(
    "project_path",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, path_type=Path),
)
@click.option(
    "--target",
    "target_language",
    default="java21",
    help="Target language for the rebuild (M1 supports only java21).",
)
@click.option(
    "--node-filter",
    default=None,
    help="fnmatch pattern applied to node FQN (e.g. '*StringUtils.reverse').",
)
@click.option(
    "--model",
    default="claude-opus-4.7",
    show_default=True,
    help="LLM model identifier; routed to provider by name prefix.",
)
def rebuild_cmd(
    project_path: Path,
    target_language: str,
    node_filter: str | None,
    model: str,
) -> None:
    """Rebuild Java methods → target_language; emit signed RebuildReceipts.

    Walks <project>/.omnix/omnix.db, dispatches one LLM call per matched
    node, runs gates 1-4 mechanically, signs the result with the project
    Ed25519 key, and writes:

        <project>/.omnix/receipts/rebuilds/<timestamp>/<node_fqn>.json
        <project>/.omnix/receipts/rebuilds/<timestamp>/<node_fqn>.sig
        <project>/.omnix/receipts/rebuilds/<timestamp>/<node_fqn>.java

    Gates 5 (property-based) and 6 (behavioral equivalence) are M2 scope;
    receipts mark them as `deferred_m2`, never `passed`.

    Requires: `omnix analyze` has been run (graph DB exists), `omnix axiom
    keygen` has been run (project key exists), and an Anthropic API key
    has been registered in the Provider Fabric vault.
    """
    from omnix.rebuild import run as rebuild_run

    outputs = rebuild_run(
        project_path=project_path.resolve(),
        target_language=target_language,
        node_filter=node_filter,
        model=model,
    )
    for o in outputs:
        click.echo(f"✓ {o.node_fqn} → {o.receipt_path}")
    click.echo(f"\n{len(outputs)} receipt(s) written.")


@click.command("impact", context_settings={"help_option_names": ["-h", "--help"]})
@click.argument("symbol")
@click.option(
    "--direction",
    type=click.Choice(["upstream", "downstream", "both"]),
    default="upstream",
    show_default=True,
)
@click.option("--depth", type=int, default=3, show_default=True)
@click.option("--include-tests/--no-include-tests", default=False, show_default=True)
@click.option("--json/--human", "as_json", default=False, show_default=True)
@click.option("--db", "db_path", type=click.Path(path_type=Path), default=None)
def impact_cmd(
    symbol: str,
    direction: str,
    depth: int,
    include_tests: bool,
    as_json: bool,
    db_path: Path | None,
) -> None:
    """Show CALLS blast radius for a symbol in the OMNIX graph."""
    import json

    from omnix.self_host_cli import (
        NoIndexError,
        UnknownSymbolError,
        impact_payload,
        render_impact_human,
        repo_root,
        resolve_db_path,
    )

    root = repo_root()
    try:
        db = resolve_db_path(root, db_path)
        payload = impact_payload(
            symbol,
            db_path=db,
            direction=direction,
            depth=depth,
            include_tests=include_tests,
        )
    except (NoIndexError, UnknownSymbolError) as exc:
        raise click.UsageError(str(exc)) from exc
    click.echo(json.dumps(payload, sort_keys=True) if as_json else render_impact_human(payload))


@click.command("detect-changes", context_settings={"help_option_names": ["-h", "--help"]})
@click.option(
    "--scope",
    type=click.Choice(["staged", "worktree", "all"]),
    default="worktree",
    show_default=True,
)
@click.option("--json/--human", "as_json", default=False, show_default=True)
@click.option("--since-commit", default=None)
@click.option("--db", "db_path", type=click.Path(path_type=Path), default=None)
def detect_changes_cmd(
    scope: str,
    as_json: bool,
    since_commit: str | None,
    db_path: Path | None,
) -> None:
    """Report git changes with symbol counts from the OMNIX graph index."""
    import json

    from omnix.self_host_cli import (
        NoIndexError,
        detect_changes_payload,
        render_detect_changes_human,
        repo_root,
        resolve_db_path,
    )

    root = repo_root()
    db: Path | None = None
    try:
        db = resolve_db_path(root, db_path)
    except NoIndexError as exc:
        if db_path is not None:
            raise click.UsageError(str(exc)) from exc
    payload = detect_changes_payload(
        root=root,
        db_path=db,
        scope=scope,
        since_commit=since_commit,
    )
    click.echo(
        json.dumps(payload, sort_keys=True)
        if as_json
        else render_detect_changes_human(payload)
    )


@click.command("status", context_settings={"help_option_names": ["-h", "--help"]})
@click.option("--db", "db_path", type=click.Path(path_type=Path), default=None)
@click.option("--json/--human", "as_json", default=False, show_default=True)
def status_cmd(db_path: Path | None, as_json: bool) -> None:
    """Report OMNIX graph index freshness for the current repository."""
    import json

    from omnix.self_host_cli import (
        NoIndexError,
        render_status_human,
        repo_root,
        resolve_db_path,
        status_payload,
    )

    root = repo_root()
    try:
        db = resolve_db_path(root, db_path)
    except NoIndexError as exc:
        raise click.UsageError(str(exc)) from exc
    payload = status_payload(root=root, db_path=db)
    click.echo(json.dumps(payload, sort_keys=True) if as_json else render_status_human(payload))


main.add_command(axiom_group, name="axiom")
main.add_command(grammar_group, name="grammar")
main.add_command(cobol_group, name="cobol")
main.add_command(analyze)
main.add_command(impact_cmd)
main.add_command(detect_changes_cmd)
main.add_command(status_cmd)
main.add_command(rebuild_cmd)


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
