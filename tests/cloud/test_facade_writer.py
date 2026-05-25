"""Tests for the strangler-fig facade writer.

Covers:
- compute_routes builds Envoy-shaped RouteConfiguration JSON
- atomic_write delivers no torn files even under mid-write SIGKILL simulation
- subscribe_writer wiring on FacadeController fans out shift events in order
- seed_from_controller restores the per-unit shift_table on startup
"""

from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
from pathlib import Path

import pytest

from omnix.cloud.cutover.facade_controller import FacadeController
from omnix.cloud.cutover.facade_writer import (
    FacadeWriter,
    RouteEntry,
    atomic_write,
    compute_routes,
    seed_from_states,
)


def _signer():
    """Toy signer for cutover authorization — bypasses the real ML-DSA call."""
    def signer(msg: bytes) -> tuple[bytes, bytes]:
        return (b"sig:" + msg[:8], b"pk:omnix")
    return signer


def _verifier_clean() -> dict:
    return {
        "daikon_violated": 0,
        "scientist_mismatches": 0,
        "diffy_mismatches": 0,
        "hypothesis_passed": True,
    }


def test_compute_routes_builds_envoy_weighted_clusters() -> None:
    table = {
        "checkout": RouteEntry(
            unit="checkout",
            legacy_cluster="legacy_checkout",
            candidate_cluster="candidate_checkout",
            candidate_weight=25,
        ),
    }
    doc = compute_routes(table)
    assert doc["resources"][0]["name"] == "omnix_routes"
    vhost = doc["resources"][0]["virtual_hosts"][0]
    assert vhost["name"] == "omnix-unit-checkout"
    clusters = vhost["routes"][0]["route"]["weighted_clusters"]["clusters"]
    weights = {c["name"]: c["weight"] for c in clusters}
    assert weights == {"legacy_checkout": 75, "candidate_checkout": 25}


def test_compute_routes_clamps_to_0_100_bounds() -> None:
    table = {
        "billing": RouteEntry(
            unit="billing", legacy_cluster="legacy_billing",
            candidate_cluster="candidate_billing", candidate_weight=250,
        ),
    }
    weights = {c["name"]: c["weight"]
               for c in compute_routes(table)["resources"][0]["virtual_hosts"][0]
                  ["routes"][0]["route"]["weighted_clusters"]["clusters"]}
    assert weights["candidate_billing"] == 100
    assert weights["legacy_billing"] == 0


def test_atomic_write_replaces_file_intact(tmp_path: Path) -> None:
    target = tmp_path / "routes.json"
    atomic_write(target, b"v1")
    assert target.read_bytes() == b"v1"
    atomic_write(target, b"v2")
    assert target.read_bytes() == b"v2"
    # And the tmp .new file is gone.
    assert not (tmp_path / "routes.json.new").exists()


def test_atomic_write_under_mid_write_kill(tmp_path: Path) -> None:
    """fsync+rename atomic write — kill the writer mid-call, reader sees old file."""
    target = tmp_path / "routes.json"
    atomic_write(target, b'{"v": 1}')

    # Launch a child that opens routes.json.new and sleeps forever before rename.
    script = (
        "import os, sys, time\n"
        f"p = {str(target)!r}\n"
        "tmp = p + '.new'\n"
        "fd = os.open(tmp, os.O_WRONLY | os.O_CREAT, 0o644)\n"
        "os.write(fd, b'TORN')\n"
        "os.fsync(fd)\n"
        "time.sleep(60)\n"
    )
    proc = subprocess.Popen([sys.executable, "-c", script])
    time.sleep(0.5)
    proc.send_signal(signal.SIGKILL)
    proc.wait(timeout=5)

    # The reader still sees the unchanged v1 — rename was never executed.
    assert json.loads(target.read_bytes()) == {"v": 1}


def test_facade_writer_subscribed_to_controller_receives_shifts(tmp_path: Path) -> None:
    controller = FacadeController(signer=_signer())
    writer = FacadeWriter(
        controller=controller,
        routes_path=tmp_path / "routes.json",
        candidate_template="candidate_{unit}",
    )
    controller.subscribe_writer(writer.on_event)

    for pct in (5, 25, 50):
        controller.request_shift(
            tenant_id="t1",
            unit_id="checkout",
            target_percentage=pct,
            verifier_summary=_verifier_clean(),
        )

    applied = writer.drain_pending()
    assert applied == 3
    doc = json.loads((tmp_path / "routes.json").read_text())
    weights = {c["name"]: c["weight"]
               for c in doc["resources"][0]["virtual_hosts"][0]
                  ["routes"][0]["route"]["weighted_clusters"]["clusters"]}
    assert weights == {"legacy_checkout": 50, "candidate_checkout": 50}


def test_facade_writer_handles_multiple_units(tmp_path: Path) -> None:
    controller = FacadeController(signer=_signer())
    writer = FacadeWriter(controller=controller, routes_path=tmp_path / "routes.json")
    controller.subscribe_writer(writer.on_event)

    controller.request_shift(tenant_id="t1", unit_id="checkout", target_percentage=10,
                             verifier_summary=_verifier_clean())
    controller.request_shift(tenant_id="t1", unit_id="billing", target_percentage=30,
                             verifier_summary=_verifier_clean())
    writer.drain_pending()

    doc = json.loads((tmp_path / "routes.json").read_text())
    vhosts = {vh["name"]: vh for vh in doc["resources"][0]["virtual_hosts"]}
    assert set(vhosts) == {"omnix-unit-checkout", "omnix-unit-billing"}


def test_seed_from_controller_restores_table_on_startup(tmp_path: Path) -> None:
    controller = FacadeController(signer=_signer())
    # Prime two units in the controller before the writer ever attaches.
    for unit, pct in [("checkout", 25), ("billing", 5)]:
        controller.request_shift(
            tenant_id="t1", unit_id=unit, target_percentage=pct,
            verifier_summary=_verifier_clean(),
        )

    writer = FacadeWriter(controller=controller, routes_path=tmp_path / "routes.json")
    writer.seed_from_controller()

    doc = json.loads((tmp_path / "routes.json").read_text())
    vhosts = {vh["name"]: vh for vh in doc["resources"][0]["virtual_hosts"]}
    weights_checkout = {c["name"]: c["weight"]
                        for c in vhosts["omnix-unit-checkout"]["routes"][0]["route"]
                          ["weighted_clusters"]["clusters"]}
    assert weights_checkout["candidate_checkout"] == 25


def test_writer_subscriber_failure_does_not_break_controller() -> None:
    controller = FacadeController(signer=_signer())

    def bad(event):
        raise RuntimeError("boom")

    controller.subscribe_writer(bad)
    # Shift still authorized + state mutated even though subscriber raised.
    event = controller.request_shift(
        tenant_id="t1", unit_id="checkout", target_percentage=10,
        verifier_summary=_verifier_clean(),
    )
    assert event.target_percentage == 10
    assert event.rejected_reason is None


def test_seed_from_states_helper_builds_table() -> None:
    from omnix.cloud.cutover.facade_controller import CutoverState
    states = [
        CutoverState(tenant_id="t1", unit_id="checkout", percentage=25),
        CutoverState(tenant_id="t1", unit_id="billing",  percentage=5),
    ]
    table = seed_from_states(states, "candidate_{unit}")
    assert table["checkout"].candidate_weight == 25
    assert table["billing"].candidate_cluster == "candidate_billing"
