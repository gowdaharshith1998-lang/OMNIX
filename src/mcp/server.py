"""OMNIX MCP Server — expose code intelligence to Claude Code, Cursor, and other MCP clients."""

from __future__ import annotations

import argparse
import json
import os
import sys


class OmnixMCPServer:
    """MCP-compatible server that exposes OMNIX tools to external AI clients."""

    def __init__(self, tools: object) -> None:
        self.tools = tools

    def handle_request(self, request: dict[str, object]) -> dict[str, object]:
        """Handle an MCP request."""
        method = str(request.get("method", ""))
        params = request.get("params")
        if not isinstance(params, dict):
            params = {}
        req_id = request.get("id")

        if method == "initialize":
            return self._response(
                req_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "omnix", "version": "0.1.0"},
                },
            )

        if method == "tools/list":
            tools = [
                {
                    "name": "omnix_search_graph",
                    "description": "Search the OMNIX knowledge graph for functions, classes, files, and their relationships",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "query": {
                                "type": "string",
                                "description": "Search query — function name, file name, or keyword",
                            },
                            "limit": {
                                "type": "integer",
                                "description": "Max results (default 20)",
                                "default": 20,
                            },
                        },
                        "required": ["query"],
                    },
                },
                {
                    "name": "omnix_trace_connections",
                    "description": "Trace all entity connections from a node — what it calls, what calls it, imports, entangled pairs",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "node_id": {
                                "type": "string",
                                "description": "Node ID from search results",
                            },
                            "depth": {
                                "type": "integer",
                                "description": "How many hops to trace (default 2)",
                                "default": 2,
                            },
                        },
                        "required": ["node_id"],
                    },
                },
                {
                    "name": "omnix_get_diagnostics",
                    "description": "Get system health diagnostics for a directory — complexity, entanglement, dark matter dependencies",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "directory": {
                                "type": "string",
                                "description": "Directory path to diagnose",
                            }
                        },
                        "required": ["directory"],
                    },
                },
                {
                    "name": "omnix_read_file",
                    "description": "Read source code from a file in the analyzed project",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Relative file path",
                            },
                            "start_line": {
                                "type": "integer",
                                "description": "Start line (optional)",
                            },
                            "end_line": {
                                "type": "integer",
                                "description": "End line (optional)",
                            },
                        },
                        "required": ["file_path"],
                    },
                },
                {
                    "name": "omnix_git_blame",
                    "description": "Get git blame info — who changed what and when",
                    "inputSchema": {
                        "type": "object",
                        "properties": {
                            "file_path": {
                                "type": "string",
                                "description": "Relative file path",
                            },
                            "line": {
                                "type": "integer",
                                "description": "Specific line number (optional)",
                            },
                        },
                        "required": ["file_path"],
                    },
                },
            ]
            return self._response(req_id, {"tools": tools})

        if method == "tools/call":
            tool_name = str(params.get("name", ""))
            args = params.get("arguments")
            if not isinstance(args, dict):
                args = {}

            tool_map = {
                "omnix_search_graph": ("search_graph", args),
                "omnix_trace_connections": ("trace_connections", args),
                "omnix_get_diagnostics": (
                    "get_diagnostics",
                    {"dir_path": args.get("directory", "")},
                ),
                "omnix_read_file": ("read_file", args),
                "omnix_git_blame": ("git_blame", args),
            }

            if tool_name not in tool_map:
                return self._error(req_id, -32602, f"Unknown tool: {tool_name}")

            real_name, real_args = tool_map[tool_name]
            execute = getattr(self.tools, "execute_tool", None)
            if not callable(execute):
                return self._error(
                    req_id, -32603, "Tools object has no execute_tool"
                )
            result = execute(real_name, **real_args)

            return self._response(
                req_id,
                {
                    "content": [
                        {"type": "text", "text": json.dumps(result, indent=2)}
                    ]
                },
            )

        return self._error(req_id, -32601, f"Unknown method: {method}")

    def _response(self, req_id: object, result: object) -> dict[str, object]:
        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    def _error(
        self, req_id: object, code: int, message: str
    ) -> dict[str, object]:
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }

    def run_stdio(self) -> None:
        """Run MCP server over stdin/stdout (newline-delimited JSON-RPC)."""
        while True:
            req_id: object | None = None
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                line = line.strip()
                if not line:
                    continue
                request = json.loads(line)
                if not isinstance(request, dict):
                    continue
                # JSON-RPC notifications omit "id"; MCP sends e.g. notifications/initialized.
                if "id" not in request:
                    continue
                req_id = request.get("id")
                response = self.handle_request(request)
                sys.stdout.write(json.dumps(response) + "\n")
                sys.stdout.flush()
            except json.JSONDecodeError:
                continue
            except Exception as e:
                err = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32603, "message": str(e)},
                }
                sys.stdout.write(json.dumps(err) + "\n")
                sys.stdout.flush()


def main() -> None:
    """Entry point for MCP server."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if root not in sys.path:
        sys.path.insert(0, root)

    parser = argparse.ArgumentParser(description="OMNIX MCP Server")
    parser.add_argument("--project", required=True, help="Path to analyzed project")
    parser.add_argument("--db", default="omnix.db", help="Path to omnix.db")
    args = parser.parse_args()

    db_path = args.db if os.path.isabs(args.db) else os.path.join(root, args.db)

    from src.agents.tools import OmnixTools

    tools = OmnixTools(args.project, db_path)
    server = OmnixMCPServer(tools)
    server.run_stdio()


if __name__ == "__main__":
    main()
