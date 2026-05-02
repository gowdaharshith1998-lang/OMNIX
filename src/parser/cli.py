"""OMNIX `grammar` CLI — read-only visibility for universal parser + evolution (Integration #11)."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections.abc import Mapping, Sequence
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import click

_EXIT_OK = 0
_EXIT_NO_DB = 1
_EXIT_NO_GRAMMAR_DATA = 2
_EXIT_INTERNAL = 3


def resolve_db_path(explicit: str | None) -> Path:
    """Walk up from CWD to find `.omnix/omnix.db`, or use `--db` path."""
    if explicit:
        p = Path(explicit).expanduser().resolve()
        if not p.is_file():
            raise FileNotFoundError(
                f"Database file not found or not a file: {p}",
            )
        return p

    cwd = Path.cwd().resolve()
    for parent in [cwd, *cwd.parents]:
        candidate = parent / ".omnix" / "omnix.db"
        if candidate.is_file():
            return candidate.resolve()

    raise FileNotFoundError(
        "No .omnix/omnix.db found in this directory or any parent. "
        "Run `omnix analyze .` (or `python omnix.py analyze <path>`) first, "
        "or pass --db /path/to/omnix.db.",
    )


def open_readonly(db_path: Path) -> sqlite3.Connection:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=30.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA query_only = 1;")
    return conn


def _iso_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def collect_grammar_status(
    conn: sqlite3.Connection,
    grammar_filter: str | None,
) -> dict[str, Any]:
    """Aggregate per-grammar rows plus footer data. All queries parameterized."""
    params: tuple[Any, ...] = ()
    where_grammar = ""
    if grammar_filter:
        where_grammar = " WHERE grammar_name = ? "
        params = (grammar_filter,)

    grammar_rows = conn.execute(
        "SELECT grammar_name, total_files_parsed, total_quality_score "
        "FROM grammar_profile" + where_grammar + " ORDER BY grammar_name",
        params,
    ).fetchall()

    grammars: list[dict[str, Any]] = []
    for row in grammar_rows:
        g = str(row["grammar_name"])
        tf = int(row["total_files_parsed"] or 0)
        tq = float(row["total_quality_score"] or 0.0)
        avg_q = round((tq / tf), 3) if tf else 0.0

        n_pat = conn.execute(
            "SELECT COUNT(*) FROM query_pattern WHERE grammar_name = ?",
            (g,),
        ).fetchone()[0]

        n_mut_30 = conn.execute(
            "SELECT COUNT(*) FROM pattern_mutation WHERE grammar_name = ? "
            "AND observed_at >= datetime('now', '-30 days')",
            (g,),
        ).fetchone()[0]

        last_r = conn.execute(
            "SELECT receipt_path FROM pattern_mutation WHERE grammar_name = ? "
            "ORDER BY observed_at DESC LIMIT 1",
            (g,),
        ).fetchone()
        receipt = ""
        if last_r and last_r[0] is not None:
            receipt = str(last_r[0]).strip()
        if not receipt:
            receipt_out: str | None = None
        else:
            receipt_out = receipt

        grammars.append(
            {
                "grammar_name": g,
                "files_parsed": tf,
                "avg_quality": avg_q,
                "parse_modes": {},
                "active_patterns": int(n_pat),
                "recent_mutations_30d": int(n_mut_30),
                "last_evolution_receipt": receipt_out,
            }
        )

    unk_rows = conn.execute(
        "SELECT extension FROM unknown_extensions ORDER BY extension ASC",
    ).fetchall()
    unknown_extensions: list[dict[str, Any]] = [
        {"ext": str(r["extension"]), "count": 1} for r in unk_rows
    ]
    top3 = [str(r["extension"]) for r in unk_rows[:3]]

    return {
        "grammars": grammars,
        "unknown_extensions": unknown_extensions,
        "unknown_extensions_top3": top3,
        "llm_fallback": {"calls": None, "budget_remaining": "n/a"},
    }


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
    """`python -m src.parser.cli status ...` — argv is full tail (e.g. ``status --json``)."""
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
    """`python -m src.parser.cli` — expects argv like `['status', '--db', ...]`."""
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


if __name__ == "__main__":
    raise SystemExit(main_module())
