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

    args = parser.parse_args()

    if args.command is None:
        parser.print_help()
        sys.exit(0)
    if args.command == "verify":
        root = os.path.dirname(os.path.abspath(__file__))
        if root not in sys.path:
            sys.path.insert(0, root)
        from src.verify import cli

        rc = int(cli.run(args))  # type: ignore[assignment, call-arg, misc, arg-type]
        sys.exit(0 if rc == 0 else 1 if rc == 1 else 2)
    if args.command != "analyze":
        print(f"Unknown command: {args.command!r}", file=sys.stderr)
        sys.exit(1)

    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    from src.parser.python_parser import parse_python_files
    from src.parser.typescript_parser import parse_typescript_files
    from src.parser.dark_matter_parser import parse_dark_matter
    from src.parser.entanglement_parser import parse_entanglements
    from src.parser.git_parser import parse_git_history
    from src.graph.store import GraphStore
    from src.graph.exporter import export_json

    target = os.path.abspath(args.path)
    db_path = os.path.join(root, "omnix.db")
    graph_json = os.path.join(root, "src", "web", "graph_data.json")
    timeline_json = os.path.join(root, "src", "web", "timeline_data.json")
    web_root = os.path.join(root, "src", "web")

    print(f"🔍 OMNIX analyzing {target}...")

    store = GraphStore(db_path)
    store.reset()

    py_count = parse_python_files(target, store)
    ts_count = parse_typescript_files(target, store)

    dm_count = parse_dark_matter(target, store)
    ent_count = parse_entanglements(target, store)

    timeline = parse_git_history(target, store)
    if timeline:
        with open(timeline_json, "w", encoding="utf-8") as f:
            json.dump(timeline, f)
        print(
            f"⏳ Timeline saved: {timeline['first_date']} → {timeline['last_date']}"
        )

    print(f"📊 Parsed {py_count} Python + {ts_count} TypeScript files")
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
        return

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
