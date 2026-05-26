"""P1 — clusters generation tests (issue #53 dispatch).

The writer must emit the per-unit Cluster list that backs the routes it
writes. Cluster names produced here MUST match the cluster names that
``compute_routes`` puts in each ``weighted_clusters`` entry, or Envoy
503s every request.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnix.cloud.cutover.facade_writer import (
    FacadeWriter,
    RouteCompositionConfig,
    RouteEntry,
    compute_clusters,
    compute_routes,
    compute_routes_and_clusters,
)


def _cfg(tmp_path: Path, *, clusters: bool = True) -> RouteCompositionConfig:
    return RouteCompositionConfig(
        routes_path=tmp_path / "routes.json",
        clusters_path=tmp_path / "clusters" / "clusters.json" if clusters else None,
        legacy_service="legacy.omnix.svc.cluster.local:80",
        candidate_service_template="omnix-candidate-{unit}.omnix.svc.cluster.local:80",
    )


def _entry(unit: str, weight: int = 0) -> RouteEntry:
    return RouteEntry(
        unit=unit,
        legacy_cluster=f"legacy_{unit}",
        candidate_cluster=f"candidate_{unit}",
        candidate_weight=weight,
    )


# -------------------- compute_clusters --------------------


def test_compute_clusters_emits_two_per_unit(tmp_path):
    config = _cfg(tmp_path)
    clusters = compute_clusters({"calc": _entry("calc"), "auth": _entry("auth")}, config)
    assert len(clusters) == 4
    names = {c["name"] for c in clusters}
    assert names == {"legacy_calc", "candidate_calc", "legacy_auth", "candidate_auth"}


def test_compute_clusters_legacy_uses_strict_dns(tmp_path):
    config = _cfg(tmp_path)
    clusters = compute_clusters({"calc": _entry("calc")}, config)
    legacy = next(c for c in clusters if c["name"] == "legacy_calc")
    assert legacy["type"] == "STRICT_DNS"


def test_compute_clusters_candidate_uses_logical_dns(tmp_path):
    """Issue #3566 — STRICT_DNS + empty hosts deadlocks Envoy. Candidates
    use LOGICAL_DNS so a not-yet-deployed candidate Service 503s cleanly
    instead of blocking cluster_manager init forever.
    """
    config = _cfg(tmp_path)
    clusters = compute_clusters({"calc": _entry("calc")}, config)
    candidate = next(c for c in clusters if c["name"] == "candidate_calc")
    assert candidate["type"] == "LOGICAL_DNS"


def test_compute_clusters_substitutes_unit_in_template(tmp_path):
    config = _cfg(tmp_path)
    clusters = compute_clusters({"payments": _entry("payments")}, config)
    candidate = next(c for c in clusters if c["name"] == "candidate_payments")
    addr = candidate["load_assignment"]["endpoints"][0]["lb_endpoints"][0]["endpoint"]["address"]["socket_address"]
    assert addr["address"] == "omnix-candidate-payments.omnix.svc.cluster.local"
    assert addr["port_value"] == 80


def test_compute_clusters_legacy_address_is_constant_across_units(tmp_path):
    config = _cfg(tmp_path)
    clusters = compute_clusters({"a": _entry("a"), "b": _entry("b")}, config)
    legacies = [c for c in clusters if c["name"].startswith("legacy_")]
    addrs = {c["load_assignment"]["endpoints"][0]["lb_endpoints"][0]["endpoint"]["address"]["socket_address"]["address"] for c in legacies}
    assert addrs == {"legacy.omnix.svc.cluster.local"}


def test_compute_clusters_sorted_by_name_for_determinism(tmp_path):
    config = _cfg(tmp_path)
    clusters = compute_clusters({"z": _entry("z"), "a": _entry("a"), "m": _entry("m")}, config)
    names = [c["name"] for c in clusters]
    # For each unit (sorted alphabetically) emit legacy_X then candidate_X
    assert names == ["legacy_a", "candidate_a", "legacy_m", "candidate_m", "legacy_z", "candidate_z"]


def test_compute_clusters_empty_shift_table_returns_empty_list(tmp_path):
    config = _cfg(tmp_path)
    assert compute_clusters({}, config) == []


def test_compute_clusters_uses_configurable_connect_timeout(tmp_path):
    config = RouteCompositionConfig(
        routes_path=tmp_path / "routes.json",
        clusters_path=tmp_path / "clusters.json",
        legacy_service="legacy:80",
        candidate_service_template="cand-{unit}:80",
        connect_timeout="3s",
    )
    clusters = compute_clusters({"calc": _entry("calc")}, config)
    assert all(c["connect_timeout"] == "3s" for c in clusters)


# -------------------- compute_routes_and_clusters lockstep --------------------


def test_compute_routes_and_clusters_names_match_lockstep(tmp_path):
    """Critical: cluster names produced by compute_clusters MUST match the
    names referenced by compute_routes' weighted_clusters entries.
    Otherwise Envoy 503s on every request.
    """
    config = _cfg(tmp_path)
    table = {"calc": _entry("calc", weight=25),
             "pay": _entry("pay", weight=50)}
    routes, clusters = compute_routes_and_clusters(table, config)
    cluster_names = {c["name"] for c in clusters}
    # Walk the routes and confirm every weighted_clusters reference exists
    referenced: set[str] = set()
    for vh in routes["resources"][0]["virtual_hosts"]:
        for r in vh["routes"]:
            for c in r["route"]["weighted_clusters"]["clusters"]:
                referenced.add(c["name"])
    assert referenced == cluster_names, (
        f"drift between routes and clusters: routes={referenced} clusters={cluster_names}"
    )


def test_compute_routes_and_clusters_returns_pair(tmp_path):
    config = _cfg(tmp_path)
    out = compute_routes_and_clusters({"calc": _entry("calc")}, config)
    assert isinstance(out, tuple)
    assert len(out) == 2
    routes, clusters = out
    assert "resources" in routes
    assert isinstance(clusters, list)


# -------------------- FacadeWriter writes both files --------------------


def test_facade_writer_dynamic_mode_writes_clusters_file(tmp_path):
    config = _cfg(tmp_path)
    writer = FacadeWriter(controller=None, config=config)
    from omnix.cloud.cutover.facade_controller import CutoverEvent
    writer.apply_event(CutoverEvent(
        event_id="e1", tenant_id="t", unit_id="calc",
        previous_percentage=0, target_percentage=25,
        verifier_summary={},
    ))
    # Both files exist
    assert (tmp_path / "routes.json").exists()
    assert (tmp_path / "clusters" / "clusters.json").exists()
    # clusters.json is a DiscoveryResponse-shaped envelope with per-unit
    # clusters
    clusters_doc = json.loads((tmp_path / "clusters" / "clusters.json").read_text())
    assert "version_info" in clusters_doc
    names = {c["name"] for c in clusters_doc["resources"]}
    assert names == {"legacy_calc", "candidate_calc"}


def test_facade_writer_static_mode_does_not_write_clusters_file(tmp_path):
    """When clusters_path=None the writer must NOT write clusters.json.

    Mode B (static) has the chart pre-render clusters inline; the writer
    must not duplicate (would cause Envoy name conflict and reject config).
    """
    config = _cfg(tmp_path, clusters=False)
    writer = FacadeWriter(controller=None, config=config)
    from omnix.cloud.cutover.facade_controller import CutoverEvent
    writer.apply_event(CutoverEvent(
        event_id="e1", tenant_id="t", unit_id="calc",
        previous_percentage=0, target_percentage=25,
        verifier_summary={},
    ))
    assert (tmp_path / "routes.json").exists()
    assert not (tmp_path / "clusters" / "clusters.json").exists()


def test_facade_writer_write_empty_produces_valid_empty_files(tmp_path):
    """write_empty() is the controller-unreachable-at-boot fallback (P3)."""
    config = _cfg(tmp_path)
    writer = FacadeWriter(controller=None, config=config)
    writer.write_empty()
    routes_doc = json.loads((tmp_path / "routes.json").read_text())
    clusters_doc = json.loads((tmp_path / "clusters" / "clusters.json").read_text())
    # Empty but VALID — Envoy boots clean, 503's until recovery
    assert routes_doc["resources"][0]["virtual_hosts"] == []
    assert clusters_doc["resources"] == []


def test_facade_writer_seed_from_units_populates_table(tmp_path):
    config = _cfg(tmp_path)
    writer = FacadeWriter(controller=None, config=config)
    writer.seed_from_units([("calc", 10), ("pay", 30)])
    routes_doc = json.loads((tmp_path / "routes.json").read_text())
    clusters_doc = json.loads((tmp_path / "clusters" / "clusters.json").read_text())
    vhost_names = {vh["name"] for vh in routes_doc["resources"][0]["virtual_hosts"]}
    assert vhost_names == {"omnix-unit-calc", "omnix-unit-pay"}
    cluster_names = {c["name"] for c in clusters_doc["resources"]}
    assert cluster_names == {"legacy_calc", "candidate_calc", "legacy_pay", "candidate_pay"}


def test_facade_writer_apply_event_uses_atomic_replace(tmp_path):
    """Writes go via .new + os.replace, so a concurrent reader sees either
    the old file or the new file — never a torn read.
    """
    config = _cfg(tmp_path)
    writer = FacadeWriter(controller=None, config=config)
    from omnix.cloud.cutover.facade_controller import CutoverEvent
    # Three successive shifts; final state must reflect the last weight only
    for pct in (10, 50, 75):
        writer.apply_event(CutoverEvent(
            event_id=f"e-{pct}", tenant_id="t", unit_id="calc",
            previous_percentage=0, target_percentage=pct,
            verifier_summary={},
        ))
    routes_doc = json.loads((tmp_path / "routes.json").read_text())
    weighted = routes_doc["resources"][0]["virtual_hosts"][0]["routes"][0]["route"]["weighted_clusters"]["clusters"]
    by_name = {c["name"]: c["weight"] for c in weighted}
    assert by_name["candidate_calc"] == 75
    assert by_name["legacy_calc"] == 25
    # No temp file left over
    assert not (tmp_path / "routes.json.new").exists()
    assert not (tmp_path / "clusters" / "clusters.json.new").exists()


def test_facade_writer_legacy_construction_still_works(tmp_path):
    """PR #47-style construction with routes_path + candidate_template only.

    The legacy path doesn't emit clusters (clusters_path stays None) — this
    is what static-mode + older tests rely on.
    """
    writer = FacadeWriter(
        controller=None,
        routes_path=tmp_path / "routes.json",
        candidate_template="candidate_{unit}",
    )
    from omnix.cloud.cutover.facade_controller import CutoverEvent
    writer.apply_event(CutoverEvent(
        event_id="e1", tenant_id="t", unit_id="calc",
        previous_percentage=0, target_percentage=10,
        verifier_summary={},
    ))
    assert (tmp_path / "routes.json").exists()
    # No clusters.json written because clusters_path is None
    assert not list(tmp_path.glob("**/clusters.json"))


def test_routecompositionconfig_writes_clusters_property(tmp_path):
    cfg_no = RouteCompositionConfig(
        routes_path=tmp_path / "r.json",
        legacy_service="l:80",
        candidate_service_template="c-{unit}:80",
    )
    cfg_yes = RouteCompositionConfig(
        routes_path=tmp_path / "r.json",
        clusters_path=tmp_path / "c.json",
        legacy_service="l:80",
        candidate_service_template="c-{unit}:80",
    )
    assert cfg_no.writes_clusters is False
    assert cfg_yes.writes_clusters is True
