"""Read-only bridge from D1 to the OMNIX Codebase-Memory graph.

The bridge attempts to import ``omnix.codebase_memory`` (the in-house code-graph
query API) and resolves column usage. If the module is not present in the
deployed env — which is the case in PR A's baseline — the bridge surfaces this
gap honestly: every lookup returns ``()`` plus a ``confidence_note`` flagging
that no usage information is available. **It never mutates the graph.**
"""

from __future__ import annotations

from typing import Tuple

from omnix.dm._types import CodebasePathUsage


def _try_import_codebase_memory():
    """Return the codebase-memory ``query`` callable, or ``None`` if the module
    is not available in this deployment. Wrapped in a function so the import
    is lazy and unit tests can monkey-patch the lookup."""
    try:
        from omnix import codebase_memory  # type: ignore[import-not-found]

        if hasattr(codebase_memory, "query"):
            return codebase_memory.query
    except ImportError:
        return None
    return None


_GRAPH_MISSING_NOTE = "codebase_memory module not deployed — column usage unknown"


def lookup_column_usage(
    table: str, column: str
) -> Tuple[Tuple[CodebasePathUsage, ...], Tuple[str, ...]]:
    """Return ``(usages, confidence_notes)`` for ``table.column``.

    Contract:
      * Never mutates the graph (read-only).
      * Never raises — graph absence or query failure surfaces as ``()`` plus
        a non-empty ``confidence_notes`` tuple so downstream confidence
        scoring can penalize the column appropriately.
    """
    query = _try_import_codebase_memory()
    if query is None:
        return (), (_GRAPH_MISSING_NOTE,)
    try:
        raw = query(
            symbol_kind="column",
            table=table,
            column=column,
        )
    except Exception as e:  # noqa: BLE001 — explicit surfacing per the honesty invariant
        return (), (f"codebase_memory query failed: {type(e).__name__}: {e}",)

    if raw is None:
        return (), (f"no code usage found for {table}.{column} — possibly orphan column",)

    usages: list[CodebasePathUsage] = []
    notes: list[str] = []
    try:
        for entry in raw:
            usages.append(
                CodebasePathUsage(
                    file_path=str(entry["file_path"]),
                    function_name=str(entry.get("function_name", "?")),
                    line_number=int(entry.get("line_number", 0)),
                    op_type=str(entry.get("op_type", "READ")),  # type: ignore[arg-type]
                )
            )
    except (KeyError, TypeError, ValueError) as e:
        notes.append(f"codebase_memory returned malformed entries: {type(e).__name__}: {e}")
    if not usages and not notes:
        notes.append(
            f"no code usage found for {table}.{column} — possibly orphan column"
        )
    return tuple(usages), tuple(notes)


__all__ = ["lookup_column_usage"]
