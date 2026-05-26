"""Strangler-fig facade writer.

Subscribes to ``FacadeController`` shift events and atomically rewrites
``/etc/envoy/routes/routes.json`` so Envoy's filesystem xDS picks the new
weights up without a pod restart. After issue #53, the writer also rewrites
``/etc/envoy/clusters/clusters.json`` so Envoy's filesystem CDS knows about
the per-unit ``legacy_{unit}`` and ``candidate_{unit}`` clusters that the
routes reference.

Atomic-write contract: write ``<file>.new``, ``fsync(fd)``,
``os.replace(new, <file>)``. POSIX guarantees that readers always see
either the old file or the new file — never a torn read.

Two modes:

- **dynamic** (default): writer emits both ``routes.json`` (RDS) and
  ``clusters.json`` (CDS). Envoy bootstrap declares filesystem CDS — no
  static cluster table — so new units appear automatically as soon as
  the controller authorizes a shift for them.
- **static**: writer emits only ``routes.json``; the chart's bootstrap
  configmap pre-renders a static cluster table from ``facade.staticUnits``.
  Used for air-gapped clusters / regulated envs.
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from omnix.cloud.cutover.facade_controller import (
    CutoverEvent,
    CutoverState,
    FacadeController,
)

logger = logging.getLogger("omnix.facade_writer")


@dataclass
class RouteEntry:
    """One unit's row in the writer's in-memory routing table.

    ``legacy_cluster`` / ``candidate_cluster`` are Envoy cluster *names*
    (e.g. ``legacy_calculator``), not addresses. The actual upstream
    address lives in ``RouteCompositionConfig`` so the writer can produce
    matching Cluster entries with the right DNS.
    """

    unit: str
    legacy_cluster: str
    candidate_cluster: str
    candidate_weight: int  # 0-100


@dataclass(frozen=True)
class RouteCompositionConfig:
    """Per-deployment composition settings.

    Single source of truth for the cluster *addresses* — both
    ``compute_routes`` and ``compute_clusters`` consume this so the names
    in routes.json and clusters.json can never drift.
    """

    routes_path: Path
    legacy_service: str
    candidate_service_template: str
    clusters_path: Path | None = None      # None => writer doesn't emit clusters (static mode)
    candidate_dns_type: str = "LOGICAL_DNS"  # see issue #3566; LOGICAL_DNS resolves lazily
    legacy_dns_type: str = "STRICT_DNS"
    connect_timeout: str = "1s"

    @property
    def writes_clusters(self) -> bool:
        return self.clusters_path is not None


def compute_routes(
    shift_table: dict[str, RouteEntry],
) -> dict:
    """Build Envoy v3 RouteConfiguration JSON from the shift table.

    Each unit becomes its own virtual host with a single weighted_cluster
    matching ``:authority`` to the unit name. Customers point their existing
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


def compute_clusters(
    shift_table: dict[str, RouteEntry],
    config: RouteCompositionConfig,
) -> list[dict]:
    """Return the Envoy Cluster list that backs ``compute_routes``' references.

    Two clusters per unit:

    - ``legacy_{unit}`` — STRICT_DNS resolved at startup. The legacy
      backend is always present, so an immediate resolve is safe.
    - ``candidate_{unit}`` — LOGICAL_DNS resolved lazily on first
      request. The candidate Deployment may not exist yet for some
      units (the operator hasn't scaffolded it). STRICT_DNS with an
      unresolvable host triggers envoyproxy/envoy#3566 — cluster_manager
      init deadlocks. LOGICAL_DNS returns 503 cleanly until the Service
      is created.

    Single source of truth with ``compute_routes`` — the cluster names
    produced here are *exactly* what ``RouteEntry.legacy_cluster`` /
    ``candidate_cluster`` reference. Drift = silent 503 on every request.
    """
    def _parse_addr(s: str) -> tuple[str, int]:
        """Parse ``host:port`` into ``(host, port_int)``.

        Conservative — only IPv4 / DNS hostnames are supported; literal IPv6
        addresses in `[::1]:80` form would require URL-parser semantics and
        Envoy's STRICT_DNS / LOGICAL_DNS types take a hostname here anyway.
        The validator below catches IPv6 brackets, non-numeric ports, and
        empty hosts; bad input becomes a clear ValueError at config time
        rather than a silent misroute at request time.
        """
        if not s:
            raise ValueError(f"empty service address")
        if s.startswith("["):
            raise ValueError(f"IPv6 literal addresses not supported in service addr: {s!r}")
        if ":" not in s:
            # No port specified — default to 80.
            return s, 80
        host, _, port_s = s.rpartition(":")
        if not host:
            raise ValueError(f"empty host in service addr: {s!r}")
        try:
            port = int(port_s)
        except ValueError as e:
            raise ValueError(
                f"non-numeric port {port_s!r} in service addr {s!r} — "
                f"named-port refs (':http') not supported, use a numeric port"
            ) from e
        if not 0 < port < 65536:
            raise ValueError(f"port out of range in service addr: {s!r}")
        return host, port

    def _cluster(name: str, addr: str, port: int, dns_type: str) -> dict:
        return {
            "@type": "type.googleapis.com/envoy.config.cluster.v3.Cluster",
            "name": name,
            "type": dns_type,
            "connect_timeout": config.connect_timeout,
            "lb_policy": "ROUND_ROBIN",
            "dns_lookup_family": "V4_ONLY",
            "load_assignment": {
                "cluster_name": name,
                "endpoints": [{
                    "lb_endpoints": [{
                        "endpoint": {
                            "address": {
                                "socket_address": {"address": addr, "port_value": port}
                            }
                        }
                    }],
                }],
            },
        }

    legacy_addr, legacy_port = _parse_addr(config.legacy_service)
    clusters: list[dict] = []
    for unit in sorted(shift_table.keys()):
        clusters.append(_cluster(
            name=f"legacy_{unit}",
            addr=legacy_addr,
            port=legacy_port,
            dns_type=config.legacy_dns_type,
        ))
        candidate_target = config.candidate_service_template.format(unit=unit)
        candidate_addr, candidate_port = _parse_addr(candidate_target)
        clusters.append(_cluster(
            name=f"candidate_{unit}",
            addr=candidate_addr,
            port=candidate_port,
            dns_type=config.candidate_dns_type,
        ))
    return clusters


def compute_routes_and_clusters(
    shift_table: dict[str, RouteEntry],
    config: RouteCompositionConfig,
) -> tuple[dict, list[dict]]:
    """Lockstep: produce both the RouteConfiguration AND the matching Cluster list.

    Use this from any production code path so names can never drift.
    ``compute_routes`` and ``compute_clusters`` remain individually callable
    for unit-test ergonomics.
    """
    return compute_routes(shift_table), compute_clusters(shift_table, config)


_VERSION_LOCK = threading.Lock()
_VERSION_COUNTER = 0


def _next_version() -> str:
    """Monotonic ``version_info`` so two writes in the same millisecond don't
    collide and get de-duped by Envoy. Counter is unix-ms-seeded so reboots
    don't start emitting old version strings.
    """
    global _VERSION_COUNTER
    with _VERSION_LOCK:
        ms = int(time.time() * 1000)
        if ms > _VERSION_COUNTER:
            _VERSION_COUNTER = ms
        else:
            _VERSION_COUNTER += 1
        return str(_VERSION_COUNTER)


def _wrap_clusters_envelope(clusters: list[dict]) -> dict:
    """Envoy filesystem CDS expects a DiscoveryResponse-shaped envelope.

    ``version_info`` is monotonic — see ``_next_version``.
    """
    return {
        "version_info": _next_version(),
        "resources": clusters,
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
            candidate_cluster=f"candidate_{state.unit_id}",
            candidate_weight=state.percentage,
        )
    return table


class FacadeWriter:
    """In-process subscriber that turns CutoverEvents into route + cluster updates.

    Two construction styles for backward-compatibility:

    - **Legacy** (PR #47): pass ``controller``, ``routes_path``,
      ``candidate_template``. The writer only emits routes.json — the
      bootstrap configmap must provide a matching static cluster table.
      (After issue #53 this path is mostly used by the static-mode
      configuration and by older tests.)
    - **Config-driven** (issue #53 dispatch): pass ``controller`` +
      ``config: RouteCompositionConfig``. If ``config.clusters_path`` is
      set, the writer also emits clusters.json on every shift — Envoy's
      filesystem CDS reads it and learns about new per-unit clusters
      without a chart rebuild.
    """

    def __init__(
        self,
        *,
        controller: FacadeController | None = None,
        config: RouteCompositionConfig | None = None,
        routes_path: str | Path | None = None,
        candidate_template: str | None = None,
    ) -> None:
        # Build a default config from legacy args so the inner code path
        # only deals with the config-driven shape.
        if config is None:
            if routes_path is None:
                raise ValueError("FacadeWriter requires either config= or routes_path=")
            config = RouteCompositionConfig(
                routes_path=Path(routes_path),
                legacy_service="legacy.default.svc.cluster.local:80",
                candidate_service_template=candidate_template or "candidate_{unit}",
                clusters_path=None,
            )
        self._controller = controller
        self._config = config
        self._lock = threading.Lock()
        self._table: dict[str, RouteEntry] = {}
        self._queue: queue.Queue[CutoverEvent] = queue.Queue()

    # --- properties ---

    @property
    def config(self) -> RouteCompositionConfig:
        return self._config

    @property
    def _routes_path(self) -> Path:
        # back-compat alias for tests written against the PR #47 surface
        return self._config.routes_path

    @property
    def _candidate_template(self) -> str:
        return self._config.candidate_service_template

    # --- subscriber API ---

    def on_event(self, event: CutoverEvent) -> None:
        """Called by the controller for each shift event."""
        self._queue.put(event)

    def apply_event(self, event: CutoverEvent) -> dict:
        """Apply one event and atomically rewrite the on-disk files.

        Returns the RouteConfiguration document for backward-compat with
        the PR #47 caller signature; in dynamic mode the matching clusters
        list is also written to ``config.clusters_path``.
        """
        # Clamp at ingest so the in-memory table and the on-disk view never
        # disagree about what was authorized (review M5).
        clamped = max(0, min(100, int(event.target_percentage)))
        with self._lock:
            entry = self._table.get(event.unit_id) or RouteEntry(
                unit=event.unit_id,
                legacy_cluster=f"legacy_{event.unit_id}",
                candidate_cluster=f"candidate_{event.unit_id}",
                candidate_weight=0,
            )
            entry.candidate_weight = clamped
            self._table[event.unit_id] = entry
            return self._recompose_locked()

    # --- bootstrap ---

    def seed_from_controller(self) -> None:
        """Initialize the in-memory routing table from the controller's state.

        Used by the in-process integration tests where writer + controller
        share a process. The sidecar runner uses HTTP seeding instead — see
        ``facade_writer_runner.seed_initial_state``.
        """
        if self._controller is None:
            raise RuntimeError("seed_from_controller requires a controller reference")
        states = list(self._controller._states.values())  # noqa: SLF001 — same-package
        with self._lock:
            self._table = seed_from_states(states, self._candidate_template)
            self._recompose_locked()

    def seed_from_units(self, units: Iterable[tuple[str, int]]) -> None:
        """Seed the routing table from ``(unit_id, percentage)`` pairs.

        Used by the sidecar runner after fetching ``GET /v1/cutover/units``.
        Clamps percentage at ingest (review M5).
        """
        with self._lock:
            for unit_id, pct in units:
                self._table[unit_id] = RouteEntry(
                    unit=unit_id,
                    legacy_cluster=f"legacy_{unit_id}",
                    candidate_cluster=f"candidate_{unit_id}",
                    candidate_weight=max(0, min(100, int(pct))),
                )
            self._recompose_locked()

    def write_empty(self) -> None:
        """Write an empty-but-valid routes.json + clusters.json.

        Used by the sidecar when the controller is unreachable at boot.
        Envoy with an empty cluster list comes up Ready and 503s every
        request — far better than deadlocking on a missing file. The next
        SSE event recovers state.
        """
        with self._lock:
            self._table.clear()
            self._recompose_locked()

    # --- write path ---

    def _recompose_locked(self) -> dict:
        routes = compute_routes(self._table)
        if self._config.writes_clusters:
            # Only compute clusters in dynamic mode — saves cycles on the
            # legacy single-file path AND avoids parsing the
            # candidate_service_template as an address when callers passed
            # a name-template ("candidate_{unit}") rather than a DNS one.
            #
            # Write CLUSTERS FIRST, then ROUTES. Envoy's CDS and RDS poll
            # filesystem mtime independently with no ordering between them.
            # If we wrote routes first, Envoy could observe the new route
            # (referencing e.g. legacy_newunit) BEFORE the new clusters file
            # appears — and respond 503 ("warming / no cluster") for the
            # gap. By writing clusters first, the cluster name a new route
            # references is guaranteed to be visible to Envoy by the time
            # the route lookup runs. (On a delete, the reverse order would
            # be needed; we currently don't delete units, only set their
            # weight to 0.)
            clusters = compute_clusters(self._table, self._config)
            envelope = _wrap_clusters_envelope(clusters)
            atomic_write(self._config.clusters_path, json.dumps(envelope, indent=2).encode())
        atomic_write(self._config.routes_path, json.dumps(routes, indent=2).encode())
        return routes

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
