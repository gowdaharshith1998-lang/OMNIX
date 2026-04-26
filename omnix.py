#!/usr/bin/env python3
"""OMNIX — Code Intelligence Engine"""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys


def _static_content_type(rel: str) -> str:
    ext = os.path.splitext(rel)[1].lower()
    overrides = {
        ".js": "application/javascript",
        ".mjs": "application/javascript",
        ".css": "text/css",
        ".json": "application/json",
        ".html": "text/html",
        ".svg": "image/svg+xml",
        ".wasm": "application/wasm",
    }
    if ext in overrides:
        base = overrides[ext]
        if ext == ".html":
            return f"{base}; charset=utf-8"
        return base
    guessed, _ = mimetypes.guess_type(rel)
    return guessed or "application/octet-stream"


def main() -> None:
    parser = argparse.ArgumentParser(description="OMNIX - Code Intelligence Engine")
    subparsers = parser.add_subparsers(dest="command")

    analyze = subparsers.add_parser("analyze", help="Analyze a codebase")
    analyze.add_argument("path", help="Path to codebase")
    analyze.add_argument(
        "--no-open",
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

    g0 = subparsers.add_parser("grammar", help="Tree-Sitter / grammar learning tools")
    g0sub = g0.add_subparsers(
        dest="grammar_sub", required=True, help="list | status | receipts | verify"
    )
    g0sub.add_parser("list", help="Installed tree_sitter_* language packages")
    gstat = g0sub.add_parser(
        "status",
        help="Per-grammar profile from a codebase omnix.db (default: ./omnix.db)",
    )
    gstat.add_argument(
        "--db",
        dest="grammar_db",
        default=None,
        help="Path to graph SQLite (default: ./omnix.db in cwd)",
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

    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    from src.parser.dark_matter_parser import parse_dark_matter
    from src.parser.entanglement_parser import parse_entanglements
    from src.parser.git_parser import parse_git_history
    from src.graph.store import GraphStore
    from src.graph.exporter import export_json
    from src.omnix_version import __version__ as omnix_v
    from src.parser import evolution
    from src.parser.ingest_dispatch import ingest_unified_codebase
    from src.parser.skip_tracking import exit_code_for_skips, format_skip_banner

    target = os.path.abspath(args.path)
    # Per-codebase graph + evolution: DB lives under the analyzed tree (Q2 / ITER 4).
    db_path = os.path.join(target, "omnix.db")
    graph_json = os.path.join(root, "src", "web", "graph_data.json")
    timeline_json = os.path.join(root, "src", "web", "timeline_data.json")
    web_root = os.path.join(root, "src", "web")

    print(f"🔍 OMNIX analyzing {target}...")

    evolution.begin_evolution_run()
    store = GraphStore(db_path)
    _ingest_tot = ingest_unified_codebase(
        target,
        store,
        force=bool(getattr(args, "force", False)),
        omnix_version=omnix_v,
    )
    _ = evolution.finalize_evolution_run(store.sqlite_connection())
    py_count = int(_ingest_tot.by_grammar.get("python", 0))
    ts_count = int(_ingest_tot.by_grammar.get("typescript", 0))

    dm_count = parse_dark_matter(target, store)
    ent_count = parse_entanglements(target, store)

    timeline = parse_git_history(target, store)
    if timeline:
        with open(timeline_json, "w", encoding="utf-8") as f:
            json.dump(timeline, f)
        print(
            f"⏳ Timeline saved: {timeline['first_date']} → {timeline['last_date']}"
        )

    print(f"📊 Parsed {py_count} Python + {ts_count} TypeScript files", end="")
    if int(getattr(_ingest_tot, "cached", 0) or 0) > 0:
        print(
            f" (unchanged, skipped: {int(_ingest_tot.cached)} files in Merkle cache)",
            end="",
        )
    print()
    _skip_banner = format_skip_banner(_ingest_tot.skip)
    if _skip_banner:
        print(_skip_banner)
    ratio_thr = float(
        args.skip_threshold if args.skip_threshold is not None else (0.5 if args.strict else 1.0)
    )
    analyze_rc = exit_code_for_skips(
        strict=bool(args.strict),
        ratio_threshold=ratio_thr,
        agg=_ingest_tot.skip,
    )
    print(f"🌀 {dm_count} dark matter nodes detected")
    print(f"⚡ {ent_count} entangled pairs detected")
    print(f"🧬 {store.node_count()} nodes, {store.edge_count()} edges")

    export_json(store, graph_json)
    store.close()

    from src.agents.orchestrator import AgentOrchestrator

    orchestrator = AgentOrchestrator(target, db_path)

    if orchestrator.available:
        print(f"🧠 AI Agent ready: {orchestrator.provider_info}")
    else:
        print(
            "🧠 AI Agent: no provider detected (set OMNIX_AI_KEY or install Ollama)"
        )

    if args.no_open:
        print(f"💾 Graph written to {graph_json}")
        if analyze_rc != 0:
            print(
                "⚠️  Analyze coverage gate: exiting with code 2 (--strict / --skip-threshold).",
                file=sys.stderr,
            )
        sys.exit(analyze_rc)

    if analyze_rc != 0:
        print(
            "⚠️  Analyze coverage gate: exiting with code 2 (--strict / --skip-threshold).",
            file=sys.stderr,
        )
        sys.exit(analyze_rc)

    import threading
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class OmnixHandler(BaseHTTPRequestHandler):
        def _write_body(self, data: bytes) -> None:
            if not getattr(self, "_omit_response_body", False):
                self.wfile.write(data)

        def _send_json(self, data: object) -> None:
            response = json.dumps(data).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(response)))
            self.send_header("Access-Control-Allow-Origin", "*")
            self.end_headers()
            self._write_body(response)

        def do_HEAD(self) -> None:
            self._omit_response_body = True
            try:
                self.do_GET()
            finally:
                self._omit_response_body = False

        def do_GET(self) -> None:
            from urllib.parse import urlparse

            path = urlparse(self.path).path
            if path == "/favicon.ico":
                self.send_response(204)
                self.end_headers()
                return
            if path == "/api/graph":
                try:
                    with open(graph_json, "rb") as f:
                        data = f.read()
                except OSError:
                    self.send_error(404, "graph_data.json missing — run analyze first")
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self._write_body(data)
                return

            if path == "/api/ai/status":
                data = {
                    "available": orchestrator.available,
                    "provider": orchestrator.provider_info,
                    "memory_stats": orchestrator.memory.get_stats(
                        orchestrator.codebase_id
                    ),
                }
                self._send_json(data)
                return

            if path == "/api/fabric/status":
                from src.fabric.handler import handle_fabric_status_get

                handle_fabric_status_get(self)
                return
            if path == "/api/fabric/telemetry":
                from src.fabric.handler import handle_fabric_telemetry_get

                handle_fabric_telemetry_get(self)
                return
            if path == "/api/fabric/spend":
                from src.fabric.handler import handle_fabric_spend_get

                handle_fabric_spend_get(self)
                return

            if path == "/api/timeline":
                try:
                    with open(timeline_json, "rb") as f:
                        data = f.read()
                except OSError:
                    self.send_error(
                        404, "timeline_data.json missing — run analyze on a git repo"
                    )
                    return
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.end_headers()
                self._write_body(data)
                return

            if path == "/" or path == "":
                path = "/index.html"
            rel = path.lstrip("/")
            if rel.replace("..", "") != rel:
                self.send_error(400, "Invalid path")
                return
            fp = os.path.join(web_root, rel)
            if not os.path.isfile(fp):
                self.send_error(404, "Not found")
                return
            with open(fp, "rb") as f:
                body = f.read()
            ctype = _static_content_type(rel)
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self._write_body(body)

        def do_POST(self) -> None:
            from urllib.parse import urlparse

            path = urlparse(self.path).path
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length) if content_length else b""

            try:
                data = json.loads(body.decode("utf-8")) if body else {}
            except json.JSONDecodeError:
                data = {}

            if not isinstance(data, dict):
                data = {}

            if path == "/api/fabric/dispatch":
                from src.fabric.handler import handle_fabric_dispatch_post

                handle_fabric_dispatch_post(self, data)
                return

            if path == "/api/vault/scan":
                from pathlib import Path

                from src.scan.handler import handle_vault_scan_post

                handle_vault_scan_post(self, project_root=Path(target))
                return
            if path == "/api/vault/scan/consume":
                from src.scan.handler import handle_vault_scan_consume_post

                handle_vault_scan_consume_post(self, data)
                return

            if path == "/api/ai/diagnose":
                dir_path = str(data.get("directory", ""))
                issue = data.get("issue")
                result = (
                    orchestrator.diagnose(dir_path, str(issue) if issue else None)
                    if orchestrator.available
                    else {"error": "AI not available"}
                )
                self._send_json(result)
                return

            if path == "/api/ai/security":
                dir_path = data.get("directory")
                result = (
                    orchestrator.security_scan(
                        str(dir_path) if dir_path is not None else None
                    )
                    if orchestrator.available
                    else {"error": "AI not available"}
                )
                self._send_json(result)
                return

            if path == "/api/ai/architecture":
                result = (
                    orchestrator.explain_architecture()
                    if orchestrator.available
                    else {"error": "AI not available"}
                )
                self._send_json(result)
                return

            if path == "/api/ai/ask":
                question = str(data.get("question", ""))
                dir_path = data.get("directory")
                result = (
                    orchestrator.ask(
                        question,
                        str(dir_path) if dir_path is not None else None,
                    )
                    if orchestrator.available
                    else {"error": "AI not available"}
                )
                self._send_json(result)
                return

            if path == "/api/ai/feedback":
                diagnosis_id = str(data.get("id", ""))
                correct = bool(data.get("correct", True))
                orchestrator.memory.mark_correct(diagnosis_id, correct)
                self._send_json({"ok": True})
                return

            self.send_error(404)

        def do_OPTIONS(self) -> None:
            self.send_response(200)
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
            self.send_header("Access-Control-Allow-Headers", "Content-Type")
            self.end_headers()

        def log_message(self, format: str, *args) -> None:
            return

    os.chdir(web_root)
    server = HTTPServer(("127.0.0.1", args.port), OmnixHandler)
    url = f"http://127.0.0.1:{args.port}/"

    print(f"🌐 OMNIX running at {url}")

    threading.Timer(0.4, lambda: webbrowser.open(url)).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n✨ OMNIX stopped")


if __name__ == "__main__":
    main()
