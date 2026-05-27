"""Foreign-key topological order for D4 table sequencing.

Kahn's algorithm with explicit cycle detection. Cycles in the FK graph are
surfaced (rare in well-formed schemas, but legal for self-referential or
deferred-constraint cases) so the orchestrator can switch to deferred-
constraint mode for affected tables.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Set, Tuple

from omnix.dm._types import SchemaSpec, TableSpec


class CycleInFKGraphError(RuntimeError):
    """Raised when topo order is impossible without deferred constraints.

    Carries the offending strongly-connected-component table names so the
    operator can decide whether to enable deferred-constraint mode.
    """

    def __init__(self, cycle_tables: Tuple[str, ...]):
        super().__init__(
            f"foreign-key cycle in tables: {cycle_tables!r}; "
            "consider deferred_constraints=True"
        )
        self.cycle_tables = cycle_tables


class DeferredConstraintWarning(UserWarning):
    """Surfaced when a self-reference forced a deferred-constraint workaround."""


class InconsistentReceiptStateError(RuntimeError):
    """Raised when D1 + D3 receipts disagree (e.g., FK targets a missing table)."""


@dataclass(frozen=True)
class TopoResult:
    order: Tuple[str, ...]
    self_referencing: Tuple[str, ...]  # surfaced as DeferredConstraintWarning
    deferred_cycle: Tuple[str, ...]    # empty unless deferred mode requested


def build_fk_topo_order(
    schema: SchemaSpec,
    *,
    allow_deferred_cycles: bool = False,
) -> TopoResult:
    """Return tables in FK-safe insert order.

    * Tables with no incoming FKs come first.
    * Self-references (table refers to itself) are tracked but allowed.
    * Cross-table cycles raise :class:`CycleInFKGraphError` unless
      ``allow_deferred_cycles=True``.
    """
    table_index: Dict[str, TableSpec] = {t.name: t for t in schema.tables}
    if not table_index:
        return TopoResult(order=(), self_referencing=(), deferred_cycle=())

    # outgoing[child] = {parents}; incoming[parent] = {children}
    outgoing: Dict[str, Set[str]] = {t: set() for t in table_index}
    incoming: Dict[str, Set[str]] = {t: set() for t in table_index}
    self_ref: List[str] = []

    for table in schema.tables:
        for fk in table.foreign_keys:
            parent = fk.to_table
            if parent not in table_index:
                raise InconsistentReceiptStateError(
                    f"FK on {table.name} targets unknown table {parent!r}"
                )
            if parent == table.name:
                self_ref.append(table.name)
                continue
            outgoing[table.name].add(parent)
            incoming[parent].add(table.name)

    # Kahn's: start from tables with no outgoing FK (depend on nothing).
    queue: List[str] = sorted(t for t in outgoing if not outgoing[t])
    order: List[str] = []
    while queue:
        # Pop smallest for deterministic output.
        queue.sort()
        node = queue.pop(0)
        order.append(node)
        for child in sorted(incoming[node]):
            outgoing[child].discard(node)
            if not outgoing[child]:
                queue.append(child)

    if len(order) != len(table_index):
        remaining = tuple(sorted(t for t in table_index if t not in order))
        if not allow_deferred_cycles:
            raise CycleInFKGraphError(remaining)
        # Append cycle members in deterministic order; operator must enable
        # deferred constraints to safely insert them.
        order.extend(remaining)
        return TopoResult(
            order=tuple(order),
            self_referencing=tuple(self_ref),
            deferred_cycle=remaining,
        )

    return TopoResult(
        order=tuple(order),
        self_referencing=tuple(self_ref),
        deferred_cycle=(),
    )


__all__ = [
    "CycleInFKGraphError",
    "DeferredConstraintWarning",
    "InconsistentReceiptStateError",
    "TopoResult",
    "build_fk_topo_order",
]
