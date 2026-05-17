"""OMNIX `grammar` CLI — read-only visibility for universal parser + evolution (Integration #11)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from typing import Any

import click

from .grammar_status_query import (
    collect_grammar_status,
    open_readonly,
    resolve_db_path,
)

_EXIT_OK = 0
_EXIT_NO_DB = 1
_EXIT_NO_GRAMMAR_DATA = 2
_EXIT_INTERNAL = 3


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _format_parse_mode_cell(_modes: Mapping[str, int]) -> str:
    """Parse-mode histogram is not persisted in the shipped schema (see evolution_schema)."""
    return "—"


def _print_table(payload: dict[str, Any]) -> None:
    grammars: Sequence[Mapping[str, Any]] = payload["grammars"]
    unk: list[dict[str, Any]] = list(payload["unknown_extensions"])
    top3: list[str] = list(payload.get("unknown_extensions_top3") or [])

    headers = (
        "Grammar",
        "Files parsed",
        "Avg quality",
        "Parse mode",
        "Active patterns",
        "Recent mutations",
        "Last evolution receipt",
    )
    rows: list[tuple[str, ...]] = []
    for g in grammars:
        last = g.get("last_evolution_receipt")
        last_s = last if isinstance(last, str) and last else "—"
        pm = _format_parse_mode_cell(g.get("parse_modes") or {})
        rows.append(
            (
                str(g["grammar_name"]),
                str(int(g["files_parsed"])),
                f"{float(g['avg_quality']):.3f}",
                pm,
                str(int(g["active_patterns"])),
                str(int(g["recent_mutations_30d"])),
                last_s,
            )
        )

    col_widths = [len(h) for h in headers]
    for r in rows:
        for i, cell in enumerate(r):
            col_widths[i] = max(col_widths[i], len(cell))

    def line(cells: tuple[str, ...]) -> str:
        parts = []
        for i, c in enumerate(cells):
            parts.append(c.ljust(col_widths[i]))
        return "  ".join(parts)

    print(line(headers))
    print(line(tuple("-" * w for w in col_widths)))
    for r in rows:
        print(line(r))

    n_unk = len(unk)
    top_s = ", ".join(top3) if top3 else "—"
    print()
    print(f"Unknown extensions: {n_unk} (top: {top_s})")

    lf = payload.get("llm_fallback") or {}
    calls = lf.get("calls")
    budget = lf.get("budget_remaining", "n/a")
    if calls is None:
        print("LLM fallback: —")
    else:
        print(f"LLM fallback: {calls} calls, ${budget} budget remaining")


def _print_json(data: dict[str, Any]) -> None:
    out = {
        "db_path": data["db_path"],
        "generated_at": data["generated_at"],
        "grammars": data["grammars"],
        "unknown_extensions": data["unknown_extensions"],
        "llm_fallback": data["llm_fallback"],
    }
    print(json.dumps(out, indent=2))


def run_grammar_status_ns(args: argparse.Namespace) -> int:
    """Used by `omnix.py` / `grammar_cmd` argparse dispatch."""
    return run_grammar_status(
        db=getattr(args, "grammar_db", None),
        as_json=bool(getattr(args, "status_json", False)),
        grammar_filter=getattr(args, "grammar_filter", None),
    )


def run_grammar_status(
    *,
    db: str | None,
    as_json: bool,
    grammar_filter: str | None,
) -> int:
    """Main entry: exit codes R5."""
    try:
        db_path = resolve_db_path(db)
    except FileNotFoundError as e:
        print(f"Error: {e}", file=sys.stderr)
        return _EXIT_NO_DB

    try:
        conn = open_readonly(db_path)
    except sqlite3.Error as e:
        print(f"Error: cannot open database (read-only): {e}", file=sys.stderr)
        return _EXIT_NO_DB

    try:
        inner = collect_grammar_status(conn, grammar_filter)
    except sqlite3.Error as e:
        print(f"Error: query failed: {e}", file=sys.stderr)
        return _EXIT_INTERNAL
    finally:
        conn.close()

    grammars = inner["grammars"]
    if grammar_filter and not grammars:
        print(
            f"No grammar data found for {grammar_filter!r}. "
            "Has this codebase been analyzed?",
            file=sys.stderr,
        )
        return _EXIT_NO_GRAMMAR_DATA
    if not grammars:
        print(
            "No grammar data found. Has this codebase been analyzed?",
            file=sys.stderr,
        )
        return _EXIT_NO_GRAMMAR_DATA

    payload: dict[str, Any] = {
        "db_path": str(db_path),
        "generated_at": _iso_now(),
        "grammars": grammars,
        "unknown_extensions": inner["unknown_extensions"],
        "llm_fallback": inner["llm_fallback"],
        "unknown_extensions_top3": inner["unknown_extensions_top3"],
    }

    if as_json:
        _print_json(payload)
    else:
        _print_table(payload)

    return _EXIT_OK


def main_argv(argv: list[str] | None) -> int:
    """`python -m omnix.parser.cli status ...` — argv is full tail (e.g. ``status --json``)."""
    p = argparse.ArgumentParser(prog="omnix grammar")
    sub = p.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("status", help="Print per-grammar parse + evolution summary.")
    st.add_argument(
        "--db",
        dest="grammar_db",
        default=None,
        help="Override DB path (default: walk up from CWD for .omnix/omnix.db).",
    )
    st.add_argument(
        "--grammar",
        dest="grammar_filter",
        default=None,
        help="Show only this grammar (e.g. python).",
    )
    st.add_argument(
        "--json",
        dest="status_json",
        action="store_true",
        help="Emit JSON instead of a table.",
    )
    st.set_defaults(func=_run_status_from_ns)
    args = p.parse_args(argv)
    return int(args.func(args))


def _run_status_from_ns(args: argparse.Namespace) -> int:
    return run_grammar_status(
        db=getattr(args, "grammar_db", None),
        as_json=bool(getattr(args, "status_json", False)),
        grammar_filter=getattr(args, "grammar_filter", None),
    )


def main_module(argv: list[str] | None = None) -> int:
    """`python -m omnix.parser.cli` — expects argv like `['status', '--db', ...]`."""
    return main_argv(argv if argv is not None else sys.argv[1:])


@click.group("grammar")
def grammar_group() -> None:
    """Grammar visibility commands."""


@grammar_group.command("status")
@click.option(
    "--db",
    "grammar_db",
    type=str,
    default=None,
    help="Override DB path (default: walk up from CWD for .omnix/omnix.db).",
)
@click.option("--grammar", "grammar_filter", default=None, help="Filter to one grammar.")
@click.option("--json", "as_json", is_flag=True, help="Emit JSON instead of a table.")
def click_status(grammar_db: str | None, grammar_filter: str | None, as_json: bool) -> None:
    db_s = grammar_db
    raise SystemExit(
        run_grammar_status(db=db_s, as_json=as_json, grammar_filter=grammar_filter)
    )


@grammar_group.command("list")
def click_list() -> None:
    from omnix.grammar_cmd import cmd_list

    raise SystemExit(cmd_list())


@grammar_group.command("receipts")
def click_receipts() -> None:
    from omnix.grammar_cmd import cmd_receipts

    raise SystemExit(cmd_receipts())


@grammar_group.command("verify")
@click.argument("receipt")
@click.option("--pubkey", default=None, type=str)
def click_verify(receipt: str, pubkey: str | None) -> None:
    from omnix.grammar_cmd import cmd_verify

    raise SystemExit(cmd_verify(receipt, pub_path=pubkey))


if __name__ == "__main__":
    raise SystemExit(main_module())
