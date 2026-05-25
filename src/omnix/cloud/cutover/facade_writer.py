"""Strangler-fig facade writer.

Subscribes to ``FacadeController`` shift events and atomically rewrites
``/etc/envoy/routes/routes.json`` so Envoy's filesystem xDS picks the new
weights up without a pod restart.

Atomic-write contract: write `routes.json.new`, ``fsync(fd)``,
``os.replace(new, routes.json)``. POSIX guarantees that readers always see
either the old file or the new file — never a torn read.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from omnix.cloud.cutover.facade_controller import (
    CutoverEvent,
    CutoverState,
    FacadeController,
)

logger = logging.getLogger("omnix.facade_writer")


@dataclass
class RouteEntry:
    unit: str
    legacy_cluster: str
    candidate_cluster: str
    candidate_weight: int  # 0-100


def compute_routes(
    shift_table: dict[str, RouteEntry],
) -> dict:
    """Build Envoy v3 RouteConfiguration JSON from the shift table.

    Each unit becomes its own virtual host with a single weighted_cluster
    matching `:authority` to the unit name. Customers point their existing
    ingress at the facade Service and rely on Host headers to route.
    """
    virtual_hosts = []
    for unit, entry in sorted(shift_table.items()):
        candidate_weight = max(0, min(100, entry.candidate_weight))
        legacy_weight = 100 - candidate_weight
        virtual_hosts.append({
            "name": f"omnix-unit-{unit}",
            "domains": [unit, f"{unit}.svc"],
            "routes": [{
                "match": {"prefix": "/"},
                "route": {
                    "weighted_clusters": {
                        "clusters": [
                            {"name": entry.legacy_cluster,    "weight": legacy_weight},
                            {"name": entry.candidate_cluster, "weight": candidate_weight},
                        ],
                        "total_weight": 100,
                    },
                },
            }],
        })
    return {
        "resources": [{
            "@type": "type.googleapis.com/envoy.config.route.v3.RouteConfiguration",
            "name": "omnix_routes",
            "virtual_hosts": virtual_hosts,
        }],
    }


def atomic_write(path: str | Path, data: bytes) -> None:
    """fsync-then-rename atomic write. Readers never see a torn file."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".new")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o644)
    try:
        os.write(fd, data)
        os.fsync(fd)
    finally:
        os.close(fd)
    os.replace(tmp, p)


def seed_from_states(states: Iterable[CutoverState],
                     candidate_template: str) -> dict[str, RouteEntry]:
    """Build the initial shift_table from the controller's seeded state."""
    table: dict[str, RouteEntry] = {}
    for state in states:
        table[state.unit_id] = RouteEntry(
            unit=state.unit_id,
            legacy_cluster=f"legacy_{state.unit_id}",
            candidate_cluster=candidate_template.format(unit=state.unit_id),
            candidate_weight=state.percentage,
        )
    return table


class FacadeWriter:
    """In-process subscriber that turns CutoverEvents into route updates."""

    def __init__(
        self,
        *,
        controller: FacadeController,
        routes_path: str | Path = "/etc/envoy/routes/routes.json",
        candidate_template: str = "candidate_{unit}",
    ) -> None:
        self._controller = controller
        self._routes_path = Path(routes_path)
        self._candidate_template = candidate_template
        self._lock = threading.Lock()
        self._table: dict[str, RouteEntry] = {}
        self._queue: queue.Queue[CutoverEvent] = queue.Queue()

    # --- subscriber API ---

    def on_event(self, event: CutoverEvent) -> None:
        """Called by the controller for each shift event."""
        self._queue.put(event)

    def apply_event(self, event: CutoverEvent) -> dict:
        """Apply one event and return the resulting routes.json document."""
        with self._lock:
            entry = self._table.get(event.unit_id) or RouteEntry(
                unit=event.unit_id,
                legacy_cluster=f"legacy_{event.unit_id}",
                candidate_cluster=self._candidate_template.format(unit=event.unit_id),
                candidate_weight=0,
            )
            entry.candidate_weight = event.target_percentage
            self._table[event.unit_id] = entry
            doc = compute_routes(self._table)
            atomic_write(self._routes_path, json.dumps(doc, indent=2).encode())
            return doc

    def drain_pending(self, *, timeout: float = 0.0) -> int:
        """Apply every queued event. Returns count applied."""
        count = 0
        deadline = time.monotonic() + timeout
        while True:
            remaining = max(0.0, deadline - time.monotonic())
            try:
                event = self._queue.get(timeout=remaining or None) if remaining > 0 else self._queue.get_nowait()
            except queue.Empty:
                break
            self.apply_event(event)
            count += 1
        return count

    # --- bootstrap ---

    def seed_from_controller(self) -> None:
        """Initialize the in-memory routing table from the controller's state."""
        states = list(self._controller._states.values())  # noqa: SLF001 — same-package introspection
        with self._lock:
            self._table = seed_from_states(states, self._candidate_template)
            doc = compute_routes(self._table)
            atomic_write(self._routes_path, json.dumps(doc, indent=2).encode())
