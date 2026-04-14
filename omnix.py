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
        action="store_true",
        help="Do not launch a browser (still serves on --port)",
    )
    analyze.add_argument("--port", type=int, default=7777, help="Web UI port")

    args = parser.parse_args()

    if args.command != "analyze":
        parser.print_help()
        sys.exit(0 if args.command is None else 1)

    root = os.path.dirname(os.path.abspath(__file__))
    if root not in sys.path:
        sys.path.insert(0, root)

    from src.parser.python_parser import parse_python_files
    from src.parser.typescript_parser import parse_typescript_files
    from src.graph.store import GraphStore
    from src.graph.exporter import export_json

    target = os.path.abspath(args.path)
    db_path = os.path.join(root, "omnix.db")
    graph_json = os.path.join(root, "src", "web", "graph_data.json")
    web_root = os.path.join(root, "src", "web")

    print(f"🔍 OMNIX analyzing {target}...")

    store = GraphStore(db_path)
    store.reset()

    py_count = parse_python_files(target, store)
    ts_count = parse_typescript_files(target, store)

    print(f"📊 Parsed {py_count} Python + {ts_count} TypeScript files")
    print(f"🧬 {store.node_count()} nodes, {store.edge_count()} edges")

    export_json(store, graph_json)
    store.close()

    if args.no_open:
        print(f"💾 Graph written to {graph_json}")
        return

    import threading
    import webbrowser
    from http.server import BaseHTTPRequestHandler, HTTPServer

    class OmnixHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:
            from urllib.parse import urlparse

            path = urlparse(self.path).path
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
                self.wfile.write(data)
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
            ctype = "text/html; charset=utf-8" if rel.endswith(".html") else "application/octet-stream"
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

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
