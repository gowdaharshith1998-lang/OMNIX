"""End-to-end strangler-fig tests against a real kind cluster.

Runs only with ``pytest --run-integration``. The cluster, build, and
helm-install setup live in ``conftest.py``; these tests then drive the
controller's POST /v1/cutover/{unit}/shift surface and assert that
production traffic actually shifts through Envoy.

The full suite is slow (~10-15 min wall time including the first
docker-build) — that's the cost of proving the chain end-to-end.
"""

from __future__ import annotations

import contextlib
import json
import socket
import subprocess
import time
from pathlib import Path

import pytest


pytestmark = pytest.mark.integration

FIXTURES_DIR = Path(__file__).parent / "fixtures"


# -------------------- helpers --------------------


def _free_port() -> int:
    with contextlib.closing(socket.socket(socket.AF_INET, socket.SOCK_STREAM)) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@contextlib.contextmanager
def _port_forward(namespace: str, service: str, target_port: int):
    """yields the local port; tears down the kubectl port-forward on exit."""
    local = _free_port()
    proc = subprocess.Popen(
        ["kubectl", "-n", namespace, "port-forward",
         f"service/{service}", f"{local}:{target_port}"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )
    try:
        # Wait for the local port to accept TCP — port-forward is async.
        deadline = time.time() + 15
        while time.time() < deadline:
            with contextlib.suppress(OSError):
                socket.create_connection(("127.0.0.1", local), timeout=1).close()
                break
            time.sleep(0.2)
        yield local
    finally:
        proc.terminate()
        with contextlib.suppress(Exception):
            proc.wait(timeout=5)


def _sample_facade(local_port: int, n: int) -> dict[str, int]:
    import httpx
    counts: dict[str, int] = {}
    for _ in range(n):
        r = httpx.get(f"http://127.0.0.1:{local_port}/", timeout=5.0)
        label = r.text.strip()
        counts[label] = counts.get(label, 0) + 1
    return counts


# -------------------- tests --------------------


def test_all_omnix_pods_reach_ready(omnix_cluster):
    """After helm install --wait, every OMNIX pod should be 1/1 or 2/2 Running."""
    out = omnix_cluster["kubectl"]("get", "pods", "--no-headers")
    lines = [ln for ln in out.split("\n") if ln.strip()]
    non_ready = []
    for ln in lines:
        cols = ln.split()
        if len(cols) < 3:
            continue
        status, ready = cols[2], cols[1]
        if status != "Running" or "/" not in ready:
            non_ready.append(ln)
            continue
        got, want = ready.split("/", 1)
        if got != want:
            non_ready.append(ln)
    assert not non_ready, f"non-Ready pods after install:\n" + "\n".join(non_ready)


def test_helm_test_smoke_pod_succeeds(omnix_cluster):
    """The vendor-managed `helm test` hook passes."""
    out = omnix_cluster["helm"](
        "test", "omnix-int",
        "--namespace", omnix_cluster["namespace"], "--logs",
    )
    assert "Phase:" in out  # helm test summary
    assert "SMOKE OK" in out


def test_cutover_shift_changes_routes_json(omnix_cluster):
    """POST /v1/cutover/test/shift updates routes.json on the facade pod."""
    namespace = omnix_cluster["namespace"]
    # Apply stubs (legacy + candidate http-echo) — see fixtures/stubs.yaml.
    omnix_cluster["kubectl"]("apply", "-f", str(FIXTURES_DIR / "stubs.yaml"))
    omnix_cluster["kubectl"](
        "wait", "--for=condition=available", "--timeout=120s",
        "deployment/legacy", "deployment/omnix-candidate-test",
    )

    with _port_forward(namespace, "omnix-int-omnix-api", 8080) as api_port:
        import httpx
        r = httpx.post(
            f"http://127.0.0.1:{api_port}/v1/cutover/test/shift",
            headers={"X-Tenant-Id": "int"},
            json={"target_percentage": 25,
                  "verifier_summary": {"scientist_mismatches": 0,
                                        "diffy_mismatches": 0,
                                        "daikon_violated": 0,
                                        "hypothesis_passed": True}},
            timeout=10.0,
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert "receipt_id" in body
        assert body["status"] == "authorized"

    # Allow the writer sidecar + Envoy filesystem RDS to pick up.
    time.sleep(5)

    pods_json = omnix_cluster["kubectl"](
        "get", "pods", "-l", "component=facade", "-o", "json"
    )
    pods = json.loads(pods_json)["items"]
    assert pods, "no facade pods found"
    facade_pod = pods[0]["metadata"]["name"]
    routes_text = omnix_cluster["kubectl"](
        "exec", facade_pod, "-c", "envoy", "--",
        "cat", "/etc/envoy/routes/routes.json",
    )
    routes = json.loads(routes_text)
    weighted = (routes["resources"][0]["virtual_hosts"][0]["routes"][0]
                ["route"]["weighted_clusters"]["clusters"])
    by_name = {c["name"]: c["weight"] for c in weighted}
    # candidate weight should reflect the 25% shift.
    assert by_name.get("candidate_test") == 25
    assert by_name.get("legacy_test") == 75


def test_traffic_shift_is_observed_through_facade(omnix_cluster):
    """Sending traffic through facade's Service shows the binomial split."""
    namespace = omnix_cluster["namespace"]
    with _port_forward(namespace, "omnix-int-omnix-facade", 8080) as facade_port:
        counts = _sample_facade(facade_port, 200)
    # 25% of 200 = 50 with binomial noise ~ ±10
    candidate = counts.get("CANDIDATE", 0)
    legacy = counts.get("LEGACY", 0)
    assert candidate + legacy >= 180, f"sample loss too high: {counts}"
    assert 35 <= candidate <= 65, f"candidate share off binomial window: {counts}"


def test_rollback_restores_legacy_only(omnix_cluster):
    """POST /v1/cutover/{unit}/rollback sets candidate weight to 0."""
    namespace = omnix_cluster["namespace"]
    with _port_forward(namespace, "omnix-int-omnix-api", 8080) as api_port:
        import httpx
        r = httpx.post(
            f"http://127.0.0.1:{api_port}/v1/cutover/test/rollback",
            headers={"X-Tenant-Id": "int"}, timeout=10.0,
        )
        assert r.status_code == 200, r.text
        assert r.json()["status"] == "rolled_back"

    time.sleep(5)
    with _port_forward(namespace, "omnix-int-omnix-facade", 8080) as facade_port:
        counts = _sample_facade(facade_port, 100)
    assert counts.get("LEGACY", 0) > 95, f"rollback didn't pin to legacy: {counts}"


def test_inline_signed_receipt_verifies_offline(omnix_cluster):
    """Round-trip: POST /v1/jobs inline+production → returned receipt verifies."""
    import base64

    from omnix.receipts.verify import verify_bytes
    namespace = omnix_cluster["namespace"]
    with _port_forward(namespace, "omnix-int-omnix-api", 8080) as api_port:
        import httpx
        r = httpx.post(
            f"http://127.0.0.1:{api_port}/v1/jobs",
            headers={"X-Tenant-Id": "int"},
            json={"source": {"workspace": "/tmp/x"},
                  "inline": True, "mode": "production"},
            timeout=30.0,
        )
        assert r.status_code == 202, r.text
        receipt = r.json()["receipts"][0]
    pk = base64.b64decode(receipt["public_key_b64"])
    sig = base64.b64decode(receipt["signature_b64"])
    canonical = base64.b64decode(receipt["payload_canonical_b64"])
    assert verify_bytes(pk, canonical, b"", sig) is True
