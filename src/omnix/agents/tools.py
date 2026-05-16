"""OMNIX Agent Tools — functions agents can call to gather information."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import urllib.request


class OmnixTools:
    """Provides tools for AI agents to query the codebase."""

    def __init__(self, project_path: str, db_path: str = "omnix.db") -> None:
        self.project_path = os.path.abspath(project_path)
        self.db_path = db_path

    def read_file(
        self,
        file_path: str,
        start_line: int | None = None,
        end_line: int | None = None,
    ) -> dict[str, object]:
        """Read a source file from the project."""
        full_path = os.path.join(self.project_path, file_path)
        if not os.path.isfile(full_path):
            return {"error": f"File not found: {file_path}"}
        try:
            with open(full_path, encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
            if start_line is not None and end_line is not None:
                lines = lines[max(0, start_line - 1) : end_line]
            content = "".join(lines[:500])
            return {"file": file_path, "lines": len(lines), "content": content}
        except OSError as e:
            return {"error": str(e)}

    def search_graph(self, query: str, limit: int = 20) -> dict[str, object]:
        """Search the code knowledge graph for nodes matching a query."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute(
                "SELECT id, name, type, file_path, start_line, end_line, complexity "
                "FROM nodes WHERE name LIKE ? OR file_path LIKE ? OR id LIKE ? LIMIT ?",
                (f"%{query}%", f"%{query}%", f"%{query}%", limit),
            )
            results = [
                {
                    "id": r[0],
                    "name": r[1],
                    "type": r[2],
                    "file": r[3],
                    "start_line": r[4],
                    "end_line": r[5],
                    "complexity": r[6],
                }
                for r in cur.fetchall()
            ]
            conn.close()
            return {"query": query, "count": len(results), "results": results}
        except (OSError, sqlite3.Error) as e:
            return {"error": str(e)}

    def trace_connections(self, node_id: str, depth: int = 2) -> dict[str, object]:
        """Trace all connections from a node up to N hops."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            visited: set[str] = set()
            trace: list[dict[str, object]] = []
            queue: list[tuple[str, int]] = [(node_id, 0)]

            while queue:
                nid, d = queue.pop(0)
                if nid in visited or d > depth:
                    continue
                visited.add(nid)

                cur.execute(
                    "SELECT target_id, relationship, metadata FROM edges WHERE source_id = ?",
                    (nid,),
                )
                for target, rel, meta in cur.fetchall():
                    trace.append(
                        {
                            "from": nid,
                            "to": target,
                            "type": rel,
                            "depth": d,
                            "metadata": meta,
                        }
                    )
                    if d < depth:
                        queue.append((target, d + 1))

                cur.execute(
                    "SELECT source_id, relationship, metadata FROM edges WHERE target_id = ?",
                    (nid,),
                )
                for source, rel, meta in cur.fetchall():
                    trace.append(
                        {
                            "from": source,
                            "to": nid,
                            "type": rel,
                            "depth": d,
                            "metadata": meta,
                        }
                    )
                    if d < depth:
                        queue.append((source, d + 1))

            conn.close()
            return {"root": node_id, "connections": len(trace), "trace": trace[:100]}
        except (OSError, sqlite3.Error) as e:
            return {"error": str(e)}

    def get_diagnostics(self, dir_path: str) -> dict[str, object]:
        """Get diagnostic issues for a directory."""
        try:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()

            cur.execute(
                "SELECT COUNT(*) FROM nodes WHERE file_path LIKE ? AND type = 'file'",
                (f"{dir_path}%",),
            )
            file_count = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(*) FROM nodes WHERE file_path LIKE ? AND type IN ('function','method','class')",
                (f"{dir_path}%",),
            )
            func_count = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(*) FROM edges WHERE relationship = 'ENTANGLED' AND (source_id LIKE ? OR target_id LIKE ?)",
                (f"{dir_path}%", f"{dir_path}%"),
            )
            entangled = cur.fetchone()[0]

            cur.execute(
                "SELECT COUNT(*) FROM edges WHERE relationship = 'DARK_FORCE' AND target_id LIKE ?",
                (f"{dir_path}%",),
            )
            dark_matter = cur.fetchone()[0]

            conn.close()
            return {
                "directory": dir_path,
                "files": file_count,
                "functions": func_count,
                "entangled_pairs": entangled,
                "dark_matter_deps": dark_matter,
            }
        except (OSError, sqlite3.Error) as e:
            return {"error": str(e)}

    def git_blame(
        self, file_path: str, line: int | None = None
    ) -> dict[str, object]:
        """Get git blame info for a file."""
        full_path = os.path.join(self.project_path, file_path)
        if not os.path.isfile(full_path):
            return {"error": f"File not found: {file_path}"}
        try:
            cmd = ["git", "blame", "--porcelain", file_path]
            if line:
                cmd.extend(["-L", f"{line},{line}"])
            result = subprocess.run(
                cmd,
                cwd=self.project_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return {"error": (result.stderr or "")[:200]}
            entries: list[dict[str, str]] = []
            current: dict[str, str] = {}
            for raw_line in result.stdout.split("\n")[:100]:
                if raw_line.startswith("author "):
                    current["author"] = raw_line[7:]
                elif raw_line.startswith("author-time "):
                    current["timestamp"] = raw_line[12:]
                elif raw_line.startswith("summary "):
                    current["message"] = raw_line[8:]
                    entries.append(current)
                    current = {}
            return {"file": file_path, "entries": entries[:20]}
        except (OSError, subprocess.SubprocessError) as e:
            return {"error": str(e)}

    def check_endpoint(
        self, url: str, method: str = "GET", timeout: int = 5
    ) -> dict[str, object]:
        """Check if a live endpoint responds."""
        try:
            req = urllib.request.Request(url, method=method)
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                chunk = resp.read(1000)
                return {
                    "url": url,
                    "status": resp.status,
                    "ok": resp.status < 400,
                    "content_length": len(chunk),
                }
        except Exception as e:
            return {"url": url, "status": 0, "ok": False, "error": str(e)}

    def list_tools(self) -> list[dict[str, object]]:
        """Return available tool definitions for LLM function calling."""
        return [
            {
                "name": "read_file",
                "description": "Read source code from a file",
                "parameters": {
                    "file_path": "string",
                    "start_line": "int (optional)",
                    "end_line": "int (optional)",
                },
            },
            {
                "name": "search_graph",
                "description": "Search the code knowledge graph for nodes",
                "parameters": {
                    "query": "string",
                    "limit": "int (optional, default 20)",
                },
            },
            {
                "name": "trace_connections",
                "description": "Trace all connections from a node up to N hops",
                "parameters": {
                    "node_id": "string",
                    "depth": "int (optional, default 2)",
                },
            },
            {
                "name": "get_diagnostics",
                "description": "Get diagnostic issues for a directory",
                "parameters": {"dir_path": "string"},
            },
            {
                "name": "git_blame",
                "description": "Get git blame info for a file",
                "parameters": {
                    "file_path": "string",
                    "line": "int (optional)",
                },
            },
            {
                "name": "check_endpoint",
                "description": "Check if a live HTTP endpoint responds",
                "parameters": {"url": "string", "method": "string (optional)"},
            },
        ]

    def execute_tool(self, tool_name: str, **kwargs: object) -> dict[str, object]:
        """Execute a tool by name."""
        tools = {
            "read_file": self.read_file,
            "search_graph": self.search_graph,
            "trace_connections": self.trace_connections,
            "get_diagnostics": self.get_diagnostics,
            "git_blame": self.git_blame,
            "check_endpoint": self.check_endpoint,
        }
        if tool_name not in tools:
            return {"error": f"Unknown tool: {tool_name}"}
        fn = tools[tool_name]
        return fn(**kwargs)
