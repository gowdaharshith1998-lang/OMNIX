"""P2 — facade chart rewrite tests (issue #53 dispatch).

Validates that:
- mode=dynamic (default) declares filesystem CDS pointing at clusters.json
- writer is a K8s 1.29+ native sidecar (initContainers + restartPolicy: Always)
- envoy mounts both routes.json and clusters.json volumes
- mode=static skips cds_config and pre-renders per-unit clusters inline
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

CHART_DIR = Path(__file__).resolve().parents[2] / "deploy" / "helm" / "omnix"

pytestmark = pytest.mark.skipif(
    shutil.which("helm") is None, reason="helm CLI not on PATH"
)


def _render(*set_args: str, release: str = "tst") -> list[dict]:
    cmd = ["helm", "template", release, str(CHART_DIR)]
    for s in set_args:
        cmd += ["--set", s]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"helm template failed: {result.stderr}"
    return [d for d in yaml.safe_load_all(result.stdout) if d]


def _envoy_bootstrap(docs: list[dict], release: str = "tst") -> dict:
    cm = next(d for d in docs
              if d.get("kind") == "ConfigMap"
              and "facade-envoy" in d.get("metadata", {}).get("name", ""))
    return yaml.safe_load(cm["data"]["envoy.yaml"])


def _facade_deployment(docs: list[dict], release: str = "tst") -> dict:
    return next(d for d in docs
                if d.get("kind") == "Deployment"
                and "facade" in d.get("metadata", {}).get("name", ""))


def _dynamic_args() -> list[str]:
    return [
        "facade.enabled=true",
        "facade.legacyService=legacy.omnix.svc:80",
        "facade.candidateServiceTemplate=omnix-candidate-{unit}.omnix.svc:80",
    ]


# -------------------- Dynamic mode (default) --------------------


def test_dynamic_mode_renders_cds_config_pointing_at_clusters_json():
    docs = _render(*_dynamic_args())
    bootstrap = _envoy_bootstrap(docs)
    assert "dynamic_resources" in bootstrap, "missing dynamic_resources block"
    assert bootstrap["dynamic_resources"]["cds_config"]["path"] == "/etc/envoy/clusters/clusters.json"


def test_dynamic_mode_has_no_static_clusters():
    """All clusters come from CDS in dynamic mode."""
    docs = _render(*_dynamic_args())
    bootstrap = _envoy_bootstrap(docs)
    assert "clusters" not in bootstrap.get("static_resources", {})


def test_dynamic_mode_listener_loads_routes_from_filesystem_rds():
    docs = _render(*_dynamic_args())
    bootstrap = _envoy_bootstrap(docs)
    listener = bootstrap["static_resources"]["listeners"][0]
    hcm = listener["filter_chains"][0]["filters"][0]["typed_config"]
    assert hcm["rds"]["config_source"]["path"] == "/etc/envoy/routes/routes.json"
    assert hcm["rds"]["route_config_name"] == "omnix_routes"


def test_dynamic_mode_writer_is_init_container_with_restartpolicy_always():
    """K8s 1.29+ native sidecar pattern — writer starts before Envoy and
    stays running for the pod lifetime. This is what guarantees the seed
    has run before Envoy reads clusters.json/routes.json.
    """
    docs = _render(*_dynamic_args())
    dep = _facade_deployment(docs)
    init = dep["spec"]["template"]["spec"]["initContainers"]
    writer = next(c for c in init if c["name"] == "writer")
    assert writer.get("restartPolicy") == "Always", (
        f"writer must be native sidecar; got restartPolicy={writer.get('restartPolicy')}"
    )


def test_dynamic_mode_writer_is_not_in_main_containers():
    """Writer must not also appear in spec.containers (would conflict)."""
    docs = _render(*_dynamic_args())
    dep = _facade_deployment(docs)
    main = dep["spec"]["template"]["spec"]["containers"]
    assert not any(c["name"] == "writer" for c in main), (
        "writer must be in initContainers, not containers"
    )


def test_dynamic_mode_envoy_mounts_clusters_volume():
    """Envoy needs read access to clusters.json for filesystem CDS."""
    docs = _render(*_dynamic_args())
    dep = _facade_deployment(docs)
    envoy = next(c for c in dep["spec"]["template"]["spec"]["containers"]
                 if c["name"] == "envoy")
    mounts = {m["name"]: m for m in envoy["volumeMounts"]}
    assert "envoy-clusters" in mounts, f"envoy missing clusters mount: {mounts.keys()}"
    assert mounts["envoy-clusters"]["readOnly"] is True


def test_dynamic_mode_writer_mounts_clusters_volume_writable():
    docs = _render(*_dynamic_args())
    dep = _facade_deployment(docs)
    writer = next(c for c in dep["spec"]["template"]["spec"]["initContainers"]
                  if c["name"] == "writer")
    mounts = {m["name"]: m for m in writer["volumeMounts"]}
    assert "envoy-clusters" in mounts
    # writer mount is RW by omission of readOnly (default false)
    assert not mounts["envoy-clusters"].get("readOnly", False)


def test_dynamic_mode_pod_has_envoy_clusters_emptydir_volume():
    docs = _render(*_dynamic_args())
    dep = _facade_deployment(docs)
    volumes = {v["name"]: v for v in dep["spec"]["template"]["spec"]["volumes"]}
    assert "envoy-clusters" in volumes
    assert "emptyDir" in volumes["envoy-clusters"]


def test_dynamic_mode_writer_env_includes_clusters_path_and_mode():
    docs = _render(*_dynamic_args())
    dep = _facade_deployment(docs)
    writer = next(c for c in dep["spec"]["template"]["spec"]["initContainers"]
                  if c["name"] == "writer")
    env = {e["name"]: e.get("value", "") for e in writer["env"]}
    assert env.get("OMNIX_FACADE_MODE") == "dynamic"
    assert env.get("OMNIX_FACADE_CLUSTERS_PATH") == "/etc/envoy/clusters/clusters.json"
    assert env.get("OMNIX_FACADE_ROUTES_PATH") == "/etc/envoy/routes/routes.json"


# -------------------- Static mode --------------------


def test_static_mode_renders_no_cds_config():
    docs = _render(
        "facade.enabled=true",
        "facade.mode=static",
        "facade.staticUnits={calculator,payments}",
        "facade.legacyService=legacy.omnix.svc:80",
        "facade.candidateServiceTemplate=omnix-candidate-{unit}.omnix.svc:80",
    )
    bootstrap = _envoy_bootstrap(docs)
    assert "dynamic_resources" not in bootstrap, (
        "static mode should not declare dynamic_resources"
    )


def test_static_mode_renders_one_legacy_one_candidate_per_unit():
    docs = _render(
        "facade.enabled=true",
        "facade.mode=static",
        "facade.staticUnits={calculator,payments,auth}",
        "facade.legacyService=legacy.omnix.svc:80",
        "facade.candidateServiceTemplate=omnix-candidate-{unit}.omnix.svc:80",
    )
    bootstrap = _envoy_bootstrap(docs)
    clusters = bootstrap["static_resources"]["clusters"]
    names = {c["name"] for c in clusters}
    assert names == {
        "legacy_calculator", "legacy_payments", "legacy_auth",
        "candidate_calculator", "candidate_payments", "candidate_auth",
    }


def test_static_mode_candidate_uses_logical_dns():
    docs = _render(
        "facade.enabled=true",
        "facade.mode=static",
        "facade.staticUnits={calculator}",
        "facade.legacyService=legacy.svc:80",
        "facade.candidateServiceTemplate=cand-{unit}.svc:80",
    )
    bootstrap = _envoy_bootstrap(docs)
    candidate = next(c for c in bootstrap["static_resources"]["clusters"]
                     if c["name"].startswith("candidate_"))
    assert candidate["type"] == "LOGICAL_DNS"


def test_static_mode_legacy_uses_strict_dns():
    docs = _render(
        "facade.enabled=true",
        "facade.mode=static",
        "facade.staticUnits={calculator}",
        "facade.legacyService=legacy.svc:80",
        "facade.candidateServiceTemplate=cand-{unit}.svc:80",
    )
    bootstrap = _envoy_bootstrap(docs)
    legacy = next(c for c in bootstrap["static_resources"]["clusters"]
                  if c["name"].startswith("legacy_"))
    assert legacy["type"] == "STRICT_DNS"


def test_static_mode_substitutes_unit_in_candidate_template():
    docs = _render(
        "facade.enabled=true",
        "facade.mode=static",
        "facade.staticUnits={calculator}",
        "facade.legacyService=legacy.svc:80",
        "facade.candidateServiceTemplate=omnix-candidate-{unit}.omnix.svc:80",
    )
    bootstrap = _envoy_bootstrap(docs)
    candidate = next(c for c in bootstrap["static_resources"]["clusters"]
                     if c["name"] == "candidate_calculator")
    addr = candidate["load_assignment"]["endpoints"][0]["lb_endpoints"][0]["endpoint"]["address"]["socket_address"]
    assert addr["address"] == "omnix-candidate-calculator.omnix.svc"
    assert addr["port_value"] == 80


def test_static_mode_does_not_mount_clusters_volume():
    docs = _render(
        "facade.enabled=true",
        "facade.mode=static",
        "facade.staticUnits={calculator}",
        "facade.legacyService=legacy.svc:80",
        "facade.candidateServiceTemplate=cand-{unit}.svc:80",
    )
    dep = _facade_deployment(docs)
    envoy = next(c for c in dep["spec"]["template"]["spec"]["containers"]
                 if c["name"] == "envoy")
    mounts = {m["name"] for m in envoy["volumeMounts"]}
    assert "envoy-clusters" not in mounts, (
        "static mode should not mount envoy-clusters (no CDS file to read)"
    )


def test_static_mode_writer_env_has_mode_static():
    docs = _render(
        "facade.enabled=true",
        "facade.mode=static",
        "facade.staticUnits={a}",
        "facade.legacyService=legacy.svc:80",
        "facade.candidateServiceTemplate=cand-{unit}.svc:80",
    )
    dep = _facade_deployment(docs)
    writer = next(c for c in dep["spec"]["template"]["spec"]["initContainers"]
                  if c["name"] == "writer")
    env = {e["name"]: e.get("value", "") for e in writer["env"]}
    assert env.get("OMNIX_FACADE_MODE") == "static"
    # No clusters path in static mode
    assert "OMNIX_FACADE_CLUSTERS_PATH" not in env
