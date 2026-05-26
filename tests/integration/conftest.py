"""Integration test scaffolding.

These tests are opt-in. Without ``--run-integration``, every test in
``tests/integration/`` is collected but skipped — so a regular
``pytest tests/`` run remains fast.

When ``--run-integration`` is passed AND docker / kind / helm / kubectl
are on PATH, the suite spins up a real kind cluster, builds the api +
studio images, helm-installs the chart, and exercises the full
controller → SSE → writer → Envoy chain.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-integration",
        action="store_true",
        default=False,
        help="run the opt-in integration suite (real kind cluster, ~10-15 min)",
    )


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-integration"):
        return
    skip_marker = pytest.mark.skip(reason="integration tests require --run-integration")
    for item in items:
        if "integration" in item.keywords:
            item.add_marker(skip_marker)


def _have_tools() -> tuple[bool, str]:
    for tool in ("docker", "kind", "helm", "kubectl"):
        if shutil.which(tool) is None:
            return False, f"{tool} not on PATH"
    # Probe the docker daemon — `docker info` exits 0 only when reachable.
    try:
        r = subprocess.run(
            ["docker", "info"], capture_output=True, text=True, timeout=10
        )
    except (subprocess.TimeoutExpired, FileNotFoundError):
        return False, "docker daemon unreachable"
    if r.returncode != 0:
        return False, f"docker daemon not running: {r.stderr.strip()[:120]}"
    return True, ""


@pytest.fixture(scope="session")
def integration_tools():
    """Verify docker + kind + helm + kubectl before any integration test runs."""
    ok, reason = _have_tools()
    if not ok:
        pytest.skip(f"integration prerequisites missing: {reason}")
    return True


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


@pytest.fixture(scope="session")
def kind_cluster_name() -> str:
    return os.environ.get("OMNIX_KIND_CLUSTER_NAME", "omnix-int")


@pytest.fixture(scope="session")
def kind_namespace() -> str:
    return os.environ.get("OMNIX_KIND_NAMESPACE", "omnix-int")


@pytest.fixture(scope="session")
def omnix_cluster(integration_tools, kind_cluster_name, kind_namespace, repo_root):
    """Provision a real kind cluster, build images, helm install the chart.

    Reuses an existing cluster of the same name when one is present
    (idempotent under repeated `pytest --run-integration` invocations).
    Yields a dict with helpers for kubectl / helm; the cluster is left
    running so subsequent runs are fast — set OMNIX_KIND_TEARDOWN=1 to
    delete it after the session.
    """
    existing = subprocess.run(
        ["kind", "get", "clusters"], capture_output=True, text=True
    ).stdout.split()
    if kind_cluster_name not in existing:
        subprocess.check_call(["kind", "create", "cluster", "--name", kind_cluster_name])

    # Build + load the api + studio images so the chart can deploy them
    # offline (Pull policy=Never in the helm install args below).
    for image, dockerfile in (
        ("omnix-api:int", "deploy/docker/api.Dockerfile"),
        ("omnix-studio:int", "deploy/docker/studio.Dockerfile"),
    ):
        subprocess.check_call(
            ["docker", "build", "-t", image, "-f", dockerfile, "."],
            cwd=str(repo_root),
        )
        subprocess.check_call(
            ["kind", "load", "docker-image", image, "--name", kind_cluster_name]
        )

    # Helm install. minio+postgres subcharts are heavy on kind; we keep
    # them enabled by default so the suite proves the vanilla path works.
    subprocess.check_call([
        "helm", "upgrade", "--install", "omnix-int",
        str(repo_root / "deploy" / "helm" / "omnix"),
        "--namespace", kind_namespace, "--create-namespace",
        "--set", "api.image.repository=omnix-api",
        "--set", "api.image.tag=int",
        "--set", "global.image.pullPolicy=Never",
        "--set", "studio.image.repository=omnix-studio",
        "--set", "studio.image.tag=int",
        "--wait", "--timeout=10m",
    ])

    def kubectl(*args: str) -> str:
        return subprocess.check_output(
            ["kubectl", "-n", kind_namespace, *args], text=True
        )

    def helm(*args: str) -> str:
        return subprocess.check_output(["helm", *args], text=True)

    info = {"name": kind_cluster_name, "namespace": kind_namespace,
            "kubectl": kubectl, "helm": helm, "repo_root": repo_root}

    yield info

    if os.environ.get("OMNIX_KIND_TEARDOWN") == "1":
        subprocess.run(["kind", "delete", "cluster", "--name", kind_cluster_name])
