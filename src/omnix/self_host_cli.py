"""Self-hosting CLI helpers for OMNIX graph impact and receipt commands."""

from __future__ import annotations

import contextlib
import json
import secrets
import sqlite3
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from omnix.omnix_version import __version__


class SelfHostError(Exception):
    """Base class for expected self-host CLI failures."""


class NoIndexError(SelfHostError):
    """No usable OMNIX graph index exists."""


class UnknownSymbolError(SelfHostError):
    """Requested symbol cannot be found in the graph index."""


@dataclass(frozen=True)
class GraphNode:
    id: str
    name: str
    type: str
    file_path: str | None
    start_line: int | None
    end_line: int | None


@dataclass(frozen=True)
class AnalyzeReceiptResult:
    receipt_path: Path
    sig_path: Path | None
    signed: bool


def _git(args: list[str], cwd: Path) -> str | None:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=15,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()


def repo_root(start: Path | None = None) -> Path:
    cwd = (start or Path.cwd()).resolve()
    out = _git(["rev-parse", "--show-toplevel"], cwd)
    if out:
        return Path(out).resolve()
    return cwd


def current_commit(root: Path) -> str | None:
    return _git(["rev-parse", "HEAD"], root)


def short_commit(commit: str | None) -> str:
    if not commit:
        return "nogit"
    return commit[:7]


def resolve_db_path(root: Path, db: Path | None = None) -> Path:
    candidates: list[Path]
    if db is not None:
        candidates = [db.expanduser()]
    else:
        cwd = Path.cwd().resolve()
        candidates = [
            root / ".omnix" / "omnix.db",
            root / "omnix.db",
            cwd / ".omnix" / "omnix.db",
            cwd / "omnix.db",
            Path.home() / ".omnix" / "omnix.db",
        ]
    for candidate in candidates:
        path = candidate.resolve()
        if path.is_file():
            return path
    raise NoIndexError("no index - run omnix analyze first")


@contextlib.contextmanager
def _connect_readonly(db_path: Path) -> Any:
    uri = f"file:{db_path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
    finally:
        conn.close()


def _read_meta(conn: sqlite3.Connection, key: str) -> str | None:
    try:
        row = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    except sqlite3.Error:
        return None
    if not row:
        return None
    return str(row[0])


def _node_from_row(row: sqlite3.Row) -> GraphNode:
    return GraphNode(
        id=str(row["id"]),
        name=str(row["name"]),
        type=str(row["type"]),
        file_path=str(row["file_path"]) if row["file_path"] is not None else None,
        start_line=int(row["start_line"]) if row["start_line"] is not None else None,
        end_line=int(row["end_line"]) if row["end_line"] is not None else None,
    )


def _load_nodes(conn: sqlite3.Connection) -> dict[str, GraphNode]:
    rows = conn.execute(
        "SELECT id, name, type, file_path, start_line, end_line FROM nodes"
    ).fetchall()
    return {str(row["id"]): _node_from_row(row) for row in rows}


def _is_test_path(file_path: str | None) -> bool:
    if not file_path:
        return False
    p = file_path.replace("\\", "/")
    name = p.rsplit("/", 1)[-1]
    return p.startswith("tests/") or "/tests/" in p or name.startswith("test_") or name.endswith("_test.py")


def _resolve_symbol(nodes: dict[str, GraphNode], symbol: str) -> GraphNode | None:
    if symbol in nodes:
        return nodes[symbol]

    if ":" in symbol and "::" not in symbol:
        file_part, name = symbol.rsplit(":", 1)
        file_part = file_part.replace("\\", "/")
        matches = [
            node
            for node in nodes.values()
            if node.name == name and (node.file_path or "").replace("\\", "/") == file_part
        ]
        if matches:
            return sorted(matches, key=lambda n: n.id)[0]

    exact_name = [node for node in nodes.values() if node.name == symbol]
    if exact_name:
        return sorted(exact_name, key=lambda n: n.id)[0]

    suffix = f"::{symbol}"
    suffix_matches = [node for node in nodes.values() if node.id.endswith(suffix)]
    if suffix_matches:
        return sorted(suffix_matches, key=lambda n: n.id)[0]

    return None


def impact_payload(
    symbol: str,
    *,
    db_path: Path,
    direction: str,
    depth: int,
    include_tests: bool,
) -> dict[str, Any]:
    if depth < 1:
        depth = 1
    with _connect_readonly(db_path) as conn:
        nodes = _load_nodes(conn)
        target = _resolve_symbol(nodes, symbol)
        if target is None:
            raise UnknownSymbolError(f"unknown symbol: {symbol}")
        edge_rows = conn.execute(
            "SELECT source_id, target_id FROM edges WHERE relationship = 'CALLS'"
        ).fetchall()

    outgoing: dict[str, set[str]] = {}
    incoming: dict[str, set[str]] = {}
    for row in edge_rows:
        source = str(row["source_id"])
        target_id = str(row["target_id"])
        outgoing.setdefault(source, set()).add(target_id)
        incoming.setdefault(target_id, set()).add(source)

    directions = ["upstream", "downstream"] if direction == "both" else [direction]
    reached: dict[tuple[str, str], int] = {}
    emitted_edges: list[dict[str, Any]] = []
    by_depth: dict[int, list[dict[str, Any]]] = {}

    for walk_direction in directions:
        frontier = {target.id}
        seen = {target.id}
        adjacency = incoming if walk_direction == "upstream" else outgoing
        for current_depth in range(1, depth + 1):
            next_frontier: set[str] = set()
            for node_id in sorted(frontier):
                for neighbor_id in sorted(adjacency.get(node_id, set())):
                    if neighbor_id in seen:
                        continue
                    neighbor = nodes.get(neighbor_id)
                    if neighbor is None:
                        continue
                    if not include_tests and _is_test_path(neighbor.file_path):
                        continue
                    seen.add(neighbor_id)
                    next_frontier.add(neighbor_id)
                    reached[(neighbor_id, walk_direction)] = current_depth
                    emitted_edges.append(
                        {
                            "source": neighbor_id if walk_direction == "upstream" else node_id,
                            "target": node_id if walk_direction == "upstream" else neighbor_id,
                            "relationship": "CALLS",
                            "depth": current_depth,
                            "direction": walk_direction,
                        }
                    )
            if not next_frontier:
                break
            frontier = next_frontier

    for (node_id, walk_direction), node_depth in sorted(
        reached.items(), key=lambda item: (item[1], item[0][0], item[0][1])
    ):
        node = nodes[node_id]
        by_depth.setdefault(node_depth, []).append(
            {
                "id": node.id,
                "name": node.name,
                "type": node.type,
                "file": node.file_path,
                "start_line": node.start_line,
                "end_line": node.end_line,
                "depth": node_depth,
                "direction": walk_direction,
            }
        )

    flat_nodes: list[dict[str, Any]] = []
    for node_depth in sorted(by_depth):
        flat_nodes.extend(by_depth[node_depth])

    return {
        "symbol": symbol,
        "target": {
            "id": target.id,
            "name": target.name,
            "file": target.file_path,
            "type": target.type,
        },
        "direction": direction,
        "depth": depth,
        "include_tests": include_tests,
        "nodes": flat_nodes,
        "edges": emitted_edges,
        "total_reachable": len({node["id"] for node in flat_nodes}),
        "total_paths": len(emitted_edges),
    }


def render_impact_human(payload: dict[str, Any]) -> str:
    target = payload["target"]
    lines = [
        f"Impact: {target['id']}",
        (
            f"Direction: {payload['direction']}  Depth: {payload['depth']}  "
            f"Include-tests: {'yes' if payload['include_tests'] else 'no'}"
        ),
        "",
    ]
    nodes = payload["nodes"]
    by_depth: dict[int, list[dict[str, Any]]] = {}
    for node in nodes:
        by_depth.setdefault(int(node["depth"]), []).append(node)
    for node_depth in sorted(by_depth):
        group = by_depth[node_depth]
        label = "direct" if node_depth == 1 else "transitive"
        lines.append(f"Depth {node_depth} ({len(group)} {label}):")
        for node in group:
            lines.append(f"  {node['id']}")
        lines.append("")
    lines.append(
        f"Total reachable: {payload['total_reachable']} nodes via {payload['total_paths']} paths"
    )
    return "\n".join(lines)


def _git_name_set(root: Path, args: list[str]) -> set[str]:
    out = _git(args, root)
    if not out:
        return set()
    return {line.strip() for line in out.splitlines() if line.strip()}


def _indexed_commit(conn: sqlite3.Connection) -> str | None:
    return _read_meta(conn, "indexed_commit")


def _file_graph_counts(conn: sqlite3.Connection, rel_path: str) -> tuple[int, int]:
    try:
        row = conn.execute(
            "SELECT node_count, edge_count FROM file_hashes WHERE file_path = ?",
            (rel_path,),
        ).fetchone()
        if row:
            return int(row["node_count"] or 0), int(row["edge_count"] or 0)
    except sqlite3.Error:
        pass
    try:
        nrow = conn.execute(
            "SELECT COUNT(*) FROM nodes WHERE file_path = ?",
            (rel_path,),
        ).fetchone()
        erow = conn.execute(
            """
            SELECT COUNT(*) FROM edges
            WHERE source_id IN (SELECT id FROM nodes WHERE file_path = ?)
               OR target_id IN (SELECT id FROM nodes WHERE file_path = ?)
            """,
            (rel_path, rel_path),
        ).fetchone()
    except sqlite3.Error:
        return 0, 0
    nodes = int(nrow[0] or 0) if nrow else 0
    edges = int(erow[0] or 0) if erow else 0
    return nodes, edges


def detect_changes_payload(
    *,
    root: Path,
    db_path: Path | None,
    scope: str,
    since_commit: str | None,
) -> dict[str, Any]:
    staged = _git_name_set(root, ["diff", "--cached", "--name-only", "--diff-filter=ACMR"])
    unstaged = _git_name_set(root, ["diff", "--name-only", "--diff-filter=ACMR"])
    untracked = _git_name_set(root, ["ls-files", "--others", "--exclude-standard"])

    indexed = since_commit
    if indexed is None and db_path is not None and db_path.is_file():
        with _connect_readonly(db_path) as conn:
            indexed = _indexed_commit(conn)

    if scope == "staged":
        changed = staged
    elif scope == "worktree":
        changed = staged | unstaged | untracked
    else:
        changed = staged | unstaged | untracked
        if indexed:
            changed |= _git_name_set(root, ["diff", "--name-only", "--diff-filter=ACMR", indexed, "HEAD"])

    file_entries: list[dict[str, Any]] = []
    for rel_path in sorted(changed):
        nodes = 0
        edges = 0
        if db_path is not None and db_path.is_file():
            with _connect_readonly(db_path) as conn:
                nodes, edges = _file_graph_counts(conn, rel_path)
        file_entries.append({"file": rel_path, "nodes": nodes, "edges": edges})

    return {
        "scope": scope,
        "since_commit": indexed,
        "files": file_entries,
        "file_count": len(file_entries),
        "node_count": sum(int(entry["nodes"]) for entry in file_entries),
        "edge_count": sum(int(entry["edges"]) for entry in file_entries),
    }


def render_detect_changes_human(payload: dict[str, Any]) -> str:
    lines = [
        f"Detected changes (scope={payload['scope']}, since-commit={payload['since_commit'] or 'unknown'}):"
    ]
    for entry in payload["files"]:
        lines.append(f"  {entry['file']}")
        lines.append(f"    +{entry['nodes']} nodes, ~{entry['edges']} edges")
    lines.append(
        f"{payload['file_count']} files, +{payload['node_count']} nodes, ~{payload['edge_count']} edges"
    )
    return "\n".join(lines)


def status_payload(*, root: Path, db_path: Path) -> dict[str, Any]:
    with _connect_readonly(db_path) as conn:
        indexed = _indexed_commit(conn)
        indexed_at = _read_meta(conn, "indexed_at")
        node_row = conn.execute("SELECT COUNT(*) FROM nodes").fetchone()
        edge_row = conn.execute("SELECT COUNT(*) FROM edges").fetchone()
        file_row = conn.execute(
            "SELECT COUNT(DISTINCT file_path) FROM nodes WHERE file_path IS NOT NULL"
        ).fetchone()
    current = current_commit(root)
    if indexed and current and indexed == current:
        status = "up-to-date"
    elif indexed and current:
        status = "stale"
    else:
        status = "unknown"
    return {
        "repository": str(root),
        "db_path": str(db_path),
        "indexed_commit": indexed,
        "indexed_at": indexed_at,
        "current_commit": current,
        "status": status,
        "node_count": int(node_row[0] or 0) if node_row else 0,
        "edge_count": int(edge_row[0] or 0) if edge_row else 0,
        "file_count": int(file_row[0] or 0) if file_row else 0,
        "last_analyze_receipt": _latest_analyze_receipt(),
    }


def render_status_human(payload: dict[str, Any]) -> str:
    indexed = payload["indexed_commit"] or "unknown"
    current = payload["current_commit"] or "unknown"
    status = payload["status"]
    if status == "stale":
        status_line = "STALE (re-run omnix analyze)"
    elif status == "up-to-date":
        status_line = "up-to-date"
    else:
        status_line = "unknown (run omnix analyze to stamp indexed commit)"
    lines = [
        f"Repository: {payload['repository']}",
        f"Indexed commit: {short_commit(indexed) if indexed != 'unknown' else indexed}"
        + (f" ({payload['indexed_at']})" if payload["indexed_at"] else ""),
        f"Current commit: {short_commit(current) if current != 'unknown' else current}",
        f"Status: {status_line}",
        "",
        (
            f"Graph: {payload['node_count']} nodes, {payload['edge_count']} edges "
            f"across {payload['file_count']} files"
        ),
    ]
    if payload["last_analyze_receipt"]:
        lines.append(f"Last analyze receipt: {payload['last_analyze_receipt']}")
    return "\n".join(lines)


def _latest_analyze_receipt() -> str | None:
    receipts_dir = Path.home() / ".omnix" / "receipts"
    try:
        receipts = sorted(receipts_dir.glob("analyze_*.json"), key=lambda p: p.stat().st_mtime)
    except OSError:
        return None
    return str(receipts[-1]) if receipts else None


def run_analyze_ingest(root: Path) -> tuple[Path, float]:
    from omnix.graph.store import GraphStore
    from omnix.parser import evolution
    from omnix.parser.ingest_dispatch import ingest_unified_codebase
    from omnix.studio.paths import project_graph_db_path

    start = time.perf_counter()
    db_path = project_graph_db_path(root)
    store = GraphStore(str(db_path))
    try:
        evolution.begin_evolution_run()
        try:
            ingest_unified_codebase(str(root), store, force=False, omnix_version=__version__)
        finally:
            with contextlib.suppress(OSError, ValueError, RuntimeError):
                evolution.finalize_evolution_run(store.sqlite_connection())
        commit = current_commit(root)
        indexed_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        if commit:
            store.set_meta("indexed_commit", commit)
        store.set_meta("indexed_at", indexed_at)
        store.commit()
    finally:
        store.close()
    return db_path, time.perf_counter() - start


def emit_analyze_receipt(root: Path, db_path: Path, wall_clock_seconds: float) -> AnalyzeReceiptResult:
    payload = _analyze_receipt_payload(root, db_path, wall_clock_seconds)
    receipt_bytes = json.dumps(payload, sort_keys=True, indent=2).encode("utf-8")
    receipt_dir = Path.home() / ".omnix" / "receipts"
    receipt_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")
    receipt_path = receipt_dir / f"analyze_{timestamp}_{short_commit(payload['git_commit'])}.json"
    receipt_path.write_bytes(receipt_bytes)

    secret_path = Path.home() / ".omnix" / "keys" / "secret.pem"
    if not secret_path.is_file():
        print("no-omnix-key-analyze-unsigned", file=sys.stderr)
        return AnalyzeReceiptResult(receipt_path=receipt_path, sig_path=None, signed=False)

    from omnix.receipts import keystore, sign

    sk = keystore.secret_from_pem(secret_path.read_text(encoding="ascii"))
    sig = sign.sign_bytes(sk, receipt_bytes, b"", secrets.token_bytes(32))
    sig_path = receipt_path.with_suffix(".sig")
    sig_path.write_text(keystore.signature_to_pem(sig), encoding="ascii")
    return AnalyzeReceiptResult(receipt_path=receipt_path, sig_path=sig_path, signed=True)


def _analyze_receipt_payload(root: Path, db_path: Path, wall_clock_seconds: float) -> dict[str, Any]:
    with _connect_readonly(db_path) as conn:
        node_count = _count(conn, "nodes")
        edge_count = _count(conn, "edges")
        file_count = _count_distinct_files(conn)
        skipped_files, skip_reasons = _skip_summary(conn)
    return {
        "kind": "omnix.analyze",
        "version": 1,
        "repo_root": str(root),
        "git_commit": current_commit(root),
        "timestamp_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "node_count": node_count,
        "edge_count": edge_count,
        "file_count": file_count,
        "skipped_files": skipped_files,
        "skip_reasons": skip_reasons,
        "grammar_versions": {},
        "omnix_version": __version__,
        "wall_clock_seconds": round(wall_clock_seconds, 6),
        "schema_uri": "https://omnix.ai/schema/analyze-receipt/v1",
    }


def _count(conn: sqlite3.Connection, table: str) -> int:
    try:
        row = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
    except sqlite3.Error:
        return 0
    return int(row[0] or 0) if row else 0


def _count_distinct_files(conn: sqlite3.Connection) -> int:
    try:
        row = conn.execute(
            "SELECT COUNT(DISTINCT file_path) FROM nodes WHERE file_path IS NOT NULL"
        ).fetchone()
    except sqlite3.Error:
        return 0
    return int(row[0] or 0) if row else 0


def _skip_summary(conn: sqlite3.Connection) -> tuple[int, dict[str, int]]:
    try:
        rows = conn.execute("SELECT extension, files FROM skip_summary").fetchall()
    except sqlite3.Error:
        return 0, {}
    reasons = {str(row["extension"]): int(row["files"] or 0) for row in rows}
    return sum(reasons.values()), reasons
