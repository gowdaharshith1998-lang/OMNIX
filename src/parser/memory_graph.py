"""In-memory graph used by parse workers (no SQLite). API mirrors :class:`GraphStore` for ingest."""

from __future__ import annotations

import json
from collections.abc import Iterator
from typing import Any

from src.graph.store import EdgeRow, NodeRow


class MemoryGraphStore:
    """Mimics :meth:`add_node` / :meth:`add_edge` / getters for universal ingest in worker processes."""

    def __init__(self) -> None:
        self._nodes: dict[str, NodeRow] = {}
        self._edges: list[EdgeRow] = []
        self._edge_sigs: set[tuple[str, str, str, str | None]] = set()
        self._next_edge_id = 1

    def commit(self) -> None:  # noqa: D401
        """No-op; compatibility with code paths that call commit on every file."""
        return

    def add_node(
        self,
        id: str,
        name: str,
        type: str,
        file_path: str | None = None,
        start_line: int | None = None,
        end_line: int | None = None,
        complexity: int = 0,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        self._nodes[id] = NodeRow(
            id=id,
            name=name,
            type=type,
            file_path=file_path,
            start_line=start_line,
            end_line=end_line,
            complexity=complexity,
            metadata=metadata,
        )

    def add_edge(
        self,
        source_id: str,
        target_id: str,
        relationship: str,
        metadata: dict[str, Any] | None = None,
    ) -> bool:
        meta_json = json.dumps(metadata, sort_keys=True) if metadata else None
        sig: tuple[str, str, str, str | None] = (
            source_id,
            target_id,
            relationship,
            meta_json,
        )
        if sig in self._edge_sigs:
            return False
        self._edge_sigs.add(sig)
        eid = self._next_edge_id
        self._next_edge_id += 1
        self._edges.append(
            EdgeRow(
                id=eid,
                source_id=source_id,
                target_id=target_id,
                relationship=relationship,
                metadata=metadata,
            )
        )
        return True

    def iter_all_nodes(self) -> Iterator[NodeRow]:
        yield from self._nodes.values()

    def iter_all_edges(self) -> Iterator[EdgeRow]:
        for e in self._edges:
            yield e

    def iter_nodes_by_file(self, file_path: str) -> Iterator[NodeRow]:
        for n in self._nodes.values():
            if n.file_path == file_path:
                yield n

    def get_all_nodes(self) -> list[NodeRow]:
        return list(self.iter_all_nodes())

    def get_all_edges(self) -> list[EdgeRow]:
        return list(self.iter_all_edges())

    def count_call_edges_for_file(self, rel: str) -> int:
        return sum(
            1
            for e in self._edges
            if e.relationship == "CALLS" and e.source_id.startswith(rel)
        )

    def node_count(self) -> int:
        return len(self._nodes)

    def edge_count(self) -> int:
        return len(self._edges)

    def count_nodes(self) -> int:
        return self.node_count()

    def count_edges(self) -> int:
        return self.edge_count()

    def to_transfer_dicts(self) -> dict[str, list[dict[str, Any]]]:
        """Serialize for IPC (pickle-friendly)."""
        node_rows: list[dict[str, Any]] = []
        for n in self._nodes.values():
            node_rows.append(
                {
                    "id": n.id,
                    "name": n.name,
                    "type": n.type,
                    "file_path": n.file_path,
                    "start_line": n.start_line,
                    "end_line": n.end_line,
                    "complexity": n.complexity,
                    "metadata": n.metadata,
                }
            )
        edge_rows: list[dict[str, Any]] = []
        for e in self._edges:
            edge_rows.append(
                {
                    "id": e.id,
                    "source_id": e.source_id,
                    "target_id": e.target_id,
                    "relationship": e.relationship,
                    "metadata": e.metadata,
                }
            )
        return {"nodes": node_rows, "edges": edge_rows}
