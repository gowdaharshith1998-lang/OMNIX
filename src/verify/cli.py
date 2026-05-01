"""`omnix verify` — argparse subcommand for property-based verification."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from .runner import ExitCode, run as verify_run


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="PBT-verify Python functions (Hypothesis, graph signals)",
    )
    p.add_argument("path", help="Path to a .py file")
    p.add_argument("--function", help="Function name (default: all top-level def)")
    p.add_argument(
        "--examples", type=int, default=200, help="Number of generated examples"
    )
    p.add_argument(
        "--json", action="store_true", help="JSON output to stdout (machine-readable)"
    )
    p.add_argument(
        "--no-receipt", action="store_true", help="Do not write receipt under ~/.omnix/receipts"
    )
    p.add_argument(
        "--graph-db", dest="graph_db", default=None, help="Path to omnix graph SQLite (default: auto-detect)"
    )
    p.add_argument(
        "--codebase-root",
        default=None,
        help="Root for relative file paths in graph (default: OMNIX repo or target parent)",
    )
    p.add_argument(
        "--verify-workspace",
        dest="verify_workspace",
        default=None,
        help="Working directory for verify (PBT relative paths land here; find_bugs sets this).",
    )
    return p


def run(args: argparse.Namespace | None = None) -> int:
    if args is None:
        a = _build_parser().parse_args()
    else:
        a = args
    fmt = "json" if a.json else "text"
    omnix_root = os.path.dirname(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    )  # .../omnix
    croot = a.codebase_root or omnix_root
    try:
        code, out = verify_run(
            str(Path(a.path).resolve()),
            function=a.function,
            examples=a.examples,
            sign=not a.no_receipt,
            output_format=fmt,
            graph_db_path=a.graph_db,
            codebase_root=croot,
            no_receipt=a.no_receipt,
            omnix_root=omnix_root,
            workspace_dir=a.verify_workspace,
        )
    except (OSError, RuntimeError) as e:
        print(f"omnix verify: {e}", file=sys.stderr)
        return int(ExitCode.ERROR)
    if out:
        print(out, end="")
    return int(code)


if __name__ == "__main__":
    raise SystemExit(run())
