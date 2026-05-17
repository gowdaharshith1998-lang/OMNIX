"""`omnix find-bugs` — argument parsing and return codes."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from . import runner


def _emit_fix_fabric_warning_if_needed(fix: bool) -> None:
    if not fix or os.environ.get("OMNIX_FUZZ_DRY") == "1":
        return
    from omnix.fabric.config import load_config
    from omnix.fabric.policy import chain_for_task

    cfg = load_config()
    chain = chain_for_task(cfg, "code_fix")
    non_ollama = [p for p in chain if str(p) != "ollama"]
    if not non_ollama:
        return
    bmap = cfg.get("budgets_usd_per_day") or {}
    try:
        cap = float(bmap.get("anthropic", 20.0))
    except (TypeError, ValueError):
        cap = 20.0
    sys.stderr.write(
        "⚠ --fix may invoke Provider Fabric (chain: "
        f"{','.join(chain)}). API spend cap: $"
        f"{cap:.2f}/day. "
        "Set OMNIX_FUZZ_DRY=1 to skip Fabric, or "
        "OMNIX_FUZZ_FABRIC_BUDGET to bound per-run calls.\n"
    )

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
        default=5,
        help="PBT examples per function (default: 5; higher = more thorough but slower)",
    )
    p.add_argument(
        "--rss-cap-mb",
        dest="rss_cap_mb",
        type=int,
        default=512,
        help="RSS memory cap per verify subprocess in MB (default: 512)",
    )
    p.add_argument(
        "--per-fn-timeout-s",
        dest="per_fn_timeout_s",
        type=int,
        default=30,
        help="Wall-clock timeout per function verify in seconds (default: 30)",
    )
    p.add_argument(
        "--total-timeout-s",
        dest="total_timeout_s",
        type=int,
        default=300,
        help="Total scan wall-clock budget in seconds (default: 300; use 0 for unbounded)",
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
        help="SQLite graph DB (default: use or create <path>/omnix.db; or set OMNIX_GRAPH_DB)",
    )
    p.add_argument(
        "--fix",
        action="store_true",
        help="Layer 7: after findings, run sandbox-only Fabric code_fix (P28); no repo writes (P27)",
    )
    p.add_argument(
        "--strict-fs-hygiene",
        action="store_true",
        help="Filesystem hygiene: snapshot entire repo depth (slower) vs depth-3 default",
    )
    p.add_argument(
        "--no-fs-hygiene",
        action="store_true",
        help="Disable filesystem hygiene detector for this scan",
    )
    p.add_argument(
        "--no-turboscan",
        action="store_true",
        help="Use legacy serial scanner (for comparison / debugging)",
    )
    p.add_argument(
        "--all",
        action="store_true",
        help="Force full scan (disable incremental file filter)",
    )
    p.add_argument(
        "--incremental",
        action="store_true",
        help="Only scan Python files changed since last successful scan",
    )
    p.add_argument(
        "--plan",
        action="store_true",
        help="Print budget plan and targets without running PBT (dry run)",
    )
    p.add_argument(
        "--emit-receipts",
        action="store_true",
        default=False,
        help="Write per-finding Ed25519 receipts and ML-DSA-signed scan manifest under ~/.omnix/receipts/findings/",
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
    _emit_fix_fabric_warning_if_needed(bool(getattr(a, "fix", False)))
    try:
        incremental = bool(getattr(a, "incremental", False))
        if bool(getattr(a, "all", False)):
            incremental = False
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
            enable_fix=bool(getattr(a, "fix", False)),
            filesystem_hygiene=not bool(getattr(a, "no_fs_hygiene", False)),
            strict_fs_hygiene=bool(getattr(a, "strict_fs_hygiene", False)),
            turboscan=not bool(getattr(a, "no_turboscan", False)),
            incremental=incremental,
            plan_only=bool(getattr(a, "plan", False)),
            emit_receipts=bool(getattr(a, "emit_receipts", False)),
            rss_cap_mb=int(getattr(a, "rss_cap_mb", 512)),
            per_fn_timeout_s=float(getattr(a, "per_fn_timeout_s", 30)),
            total_timeout_s=float(getattr(a, "total_timeout_s", 300)),
        )
    except (OSError, RuntimeError, TypeError) as e:
        print(f"omnix find-bugs: {e}", file=sys.stderr)
        return _EXIT_ERR
    if ex == 2:
        if out:
            if bool(getattr(a, "json", False)):
                print(out, end="")
            else:
                print(out, end="", file=sys.stderr)
        return _EXIT_ERR
    if out:
        if a.json:
            print(out, end="")
        else:
            end = "" if out.endswith("\n") else "\n"
            print(out, end=end, file=sys.stdout)
    return ex
