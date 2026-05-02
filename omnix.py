#!/usr/bin/env python3
"""OMNIX — Code Intelligence Engine"""

from __future__ import annotations

import argparse
import os
import sys


def main() -> None:
    parser = argparse.ArgumentParser(description="OMNIX - Code Intelligence Engine")
    subparsers = parser.add_subparsers(dest="command")

    analyze = subparsers.add_parser("analyze", help="Analyze a codebase")
    analyze.add_argument("path", help="Path to codebase")
    analyze.add_argument(
        "--no-open",
        "--no-browser",
        dest="no_open",
        action="store_true",
        help="Do not launch a browser (still serves on --port)",
    )
    analyze.add_argument("--port", type=int, default=7777, help="Web UI port")
    analyze.add_argument(
        "--strict",
        action="store_true",
        help="Exit 2 if any grammar package is missing (no_grammar skips) or >50%% of est. LOC was skipped",
    )
    analyze.add_argument(
        "--skip-threshold",
        type=float,
        default=None,
        metavar="N",
        help="Exit 2 when skipped_est_loc / total_loc > N (0.0–1.0). "
        "Default: 1.0 (off) without --strict; 0.5 with --strict unless you pass this flag.",
    )
    analyze.add_argument(
        "--force",
        action="store_true",
        help="Re-parse all files (bypasses content hash + profile/version change detection)",
    )

    vsub = subparsers.add_parser(
        "verify", help="Property-based test / verify a Python function"
    )
    vsub.add_argument("path", help="Path to a .py file")
    vsub.add_argument(
        "--function", default=None, help="Specific function name (else all top-level)"
    )
    vsub.add_argument(
        "--examples", type=int, default=200, help="Number of test examples (default: 200)"
    )
    vsub.add_argument(
        "--json", action="store_true", help="JSON output to stdout (machine-readable)"
    )
    vsub.add_argument(
        "--no-receipt",
        action="store_true",
        help="Skip writing signed receipt to ~/.omnix/receipts",
    )
    vsub.add_argument(
        "--graph-db", dest="graph_db", default=None, help="Path to graph SQLite (default: auto-detect)"
    )
    vsub.add_argument(
        "--codebase-root", default=None, help="Analyzed root for rel paths in graph (default: OMNIX repo root)"
    )
    vsub.add_argument(
        "--verify-workspace",
        default=None,
        help="Working directory for verify (relative paths from PBT land here; find-bugs sets this automatically).",
    )

    fb = subparsers.add_parser("find-bugs", help="Scan a codebase for bugs (PBT + graph ranking)")
    fb.add_argument("path", help="Path to codebase root")
    fb.add_argument("--examples", type=int, default=50, help="PBT examples per function (default: 50)")
    fb.add_argument(
        "--top", type=int, default=10, help="Max findings in text summary (default: 10)"
    )
    fb.add_argument("--json", action="store_true", help="Print signed bundle JSON to stdout")
    fb.add_argument(
        "--no-bundle",
        action="store_true",
        help="Do not write a bundle to ~/.omnix/receipts",
    )
    fb.add_argument(
        "--include-private",
        action="store_true",
        help="Verify top-level names starting with underscore",
    )
    fb.add_argument(
        "--max-file-size", type=int, default=1_000_000, help="Skip .py files larger than this (bytes)"
    )
    fb.add_argument(
        "--graph-db", dest="graph_db", default=None, help="SQLite graph DB (optional override)"
    )
    fb.add_argument(
        "--fix",
        action="store_true",
        help="Layer 7: run sandbox-only Fabric code_fix for the top fixable finding (P28); no direct repo writes",
    )
    fb.add_argument(
        "--emit-receipts",
        action="store_true",
        default=False,
        help="Write per-finding cryptographic receipts + ML-DSA scan manifest under ~/.omnix/receipts/findings/",
    )

    g0 = subparsers.add_parser("grammar", help="Tree-Sitter / grammar learning tools")
    g0sub = g0.add_subparsers(
        dest="grammar_sub", required=True, help="list | status | receipts | verify"
    )
    g0sub.add_parser("list", help="Installed tree_sitter_* language packages")
    gstat = g0sub.add_parser(
        "status",
        help="Per-grammar profile from .omnix/omnix.db (walk up from cwd; override with --db)",
    )
    gstat.add_argument(
        "--db",
        dest="grammar_db",
        default=None,
        help="Path to omnix SQLite (default: find .omnix/omnix.db upward from cwd)",
    )
    gstat.add_argument(
        "--json",
        dest="status_json",
        action="store_true",
        help="Emit JSON instead of a table",
    )
    gstat.add_argument(
        "--grammar",
        dest="grammar_filter",
        default=None,
        help="Show only this grammar (e.g. python)",
    )
    g0sub.add_parser(
        "receipts",
        help="List signed evolution JSON receipts in ~/.omnix/receipts",
    )
    gver = g0sub.add_parser(
        "verify",
        help="Verify ML-DSA-65 on an evolution JSON (default ~/.omnix/keys/public.pem)",
    )
    gver.add_argument("receipt", help="Path to evolution_*.json")
    gver.add_argument(
        "--pubkey",
        type=str,
        default=None,
        help="public.pem (default: ~/.omnix/keys/public.pem)",
    )

    st = subparsers.add_parser("studio", help="OMNIX Studio live graph workspace (FastAPI on :7778 default)")
    st.add_argument("path", nargs="?", default=None, help="Project root to open (optional; welcome screen if omitted)")
    st.add_argument(
        "--port",
        type=int,
        default=None,
        help="Server port (default: 7778, override with OMNIX_STUDIO_PORT env)",
    )

    if len(sys.argv) > 1 and sys.argv[1] == "axiom":
        root_om = os.path.dirname(os.path.abspath(__file__))
        if root_om not in sys.path:
            sys.path.insert(0, root_om)
        from axiom.cli import axiom_group

        sys.exit(
            axiom_group.main(  # type: ignore[union-attr, misc, arg-type]
                args=sys.argv[2:],
                prog_name="omnix axiom",
            )
        )

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)
    root_om = os.path.dirname(os.path.abspath(__file__))
    if args.command == "grammar":
        if root_om not in sys.path:
            sys.path.insert(0, root_om)
        from src.grammar_cmd import run_grammar

        sys.exit(int(run_grammar(args)))
    if args.command == "find-bugs":
        if root_om not in sys.path:
            sys.path.insert(0, root_om)
        from src.find_bugs import cli as _fb

        rc = int(_fb.run(args))  # type: ignore[call-arg, misc, arg-type, assignment, assignment, unused-ignore, unused-ignore]
        sys.exit(0 if rc == 0 else 1 if rc == 1 else 2)
    if args.command == "verify":
        root = root_om
        if root not in sys.path:
            sys.path.insert(0, root)
        from src.verify import cli

        rc = int(cli.run(args))  # type: ignore[assignment, call-arg, misc, arg-type]
        sys.exit(0 if rc == 0 else 1 if rc == 1 else 2)
    if args.command == "studio":
        if root_om not in sys.path:
            sys.path.insert(0, root_om)
        from src.studio.server import run as studio_run  # type: ignore[import-not-found, no-untyped-def, misc, no-untyped-def, no-any-return]  # noqa: E501

        pp: str | None
        if args.path:  # noqa: E501
            pp = os.path.abspath(str(args.path))  # type: ignore[no-untyped-def, misc, no-untyped-def, no-any-return]  # noqa: E501, E501
        else:  # noqa: E501
            pp = None
        studio_run(project_path=pp, port=getattr(args, "port", None))  # type: ignore[no-untyped-def, misc, no-untyped-def, no-untyped-def, no-any-return]  # noqa: E501, E501
        sys.exit(0)
    if args.command != "analyze":
        print(f"Unknown command: {args.command!r}", file=sys.stderr)
        sys.exit(1)

    _st = args.skip_threshold
    if _st is not None and not (0.0 <= _st <= 1.0):
        parser.error("--skip-threshold must be between 0.0 and 1.0")

    target = os.path.abspath(args.path)
    import threading
    import webbrowser

    if root_om not in sys.path:
        sys.path.insert(0, root_om)
    from src.studio.server import run as studio_run  # type: ignore[import-not-found]

    url = f"http://127.0.0.1:{args.port}/"

    print(f"🌐 OMNIX running at {url}")

    if not args.no_open:
        threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        studio_run(project_path=target, port=args.port)
    except KeyboardInterrupt:
        print("\n✨ OMNIX stopped")


if __name__ == "__main__":
    main()
