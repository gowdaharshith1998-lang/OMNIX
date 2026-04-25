"""`omnix find-bugs` — argument parsing and return codes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import runner

_EXIT_OK = 0
_EXIT_FAIL = 1
_EXIT_ERR = 2


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Scan a Python codebase for bugs via PBT and graph-based ranking"
    )
    p.add_argument("path", help="Path to codebase root")
    p.add_argument(
        "--examples",
        type=int,
        default=50,
        help="PBT examples per function (default: 50)",
    )
    p.add_argument(
        "--top", type=int, default=10, help="Max findings in text summary (default: 10)"
    )
    p.add_argument(
        "--json", action="store_true", help="Print signed bundle JSON to stdout"
    )
    p.add_argument(
        "--no-bundle",
        action="store_true",
        help="Do not write bundle under ~/.omnix/receipts (text mode skips signing too)",
    )
    p.add_argument(
        "--include-private",
        action="store_true",
        help="Also verify top-level names starting with underscore",
    )
    p.add_argument(
        "--max-file-size",
        type=int,
        default=1_000_000,
        help="Skip .py files larger than this (default: 1_000_000 bytes)",
    )
    p.add_argument(
        "--graph-db",
        dest="graph_db",
        default=None,
        help="SQLite graph DB (default: <path>/omnix.db or ~/.omnix/omnix.db)",
    )
    return p


def run(
    args: argparse.Namespace | None = None, argv: list[str] | None = None
) -> int:
    if args is None:
        a = _build_parser().parse_args(argv) if argv else _build_parser().parse_args()
    else:
        a = args
    path = str(Path(a.path).resolve())
    g = a.graph_db
    if g:
        g = str(Path(g).resolve())
    try:
        ex, out, _detail = runner.run_find_bugs(
            path,
            examples=a.examples,
            top=a.top,
            json_mode=bool(a.json),
            no_bundle=bool(a.no_bundle),
            include_private=bool(a.include_private),
            max_file_size=int(a.max_file_size),
            graph_db=g,
            no_sign=False,
        )
    except (OSError, RuntimeError, TypeError) as e:
        print(f"omnix find-bugs: {e}", file=sys.stderr)
        return _EXIT_ERR
    if ex == 2:
        if out:
            print(out, end="", file=sys.stderr)
        return _EXIT_ERR
    if out:
        if a.json:
            print(out, end="")
        else:
            end = "" if out.endswith("\n") else "\n"
            print(out, end=end, file=sys.stdout)
    return ex
