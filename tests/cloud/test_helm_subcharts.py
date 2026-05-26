"""P5 — Postgres + MinIO opt-in subchart tests.

These exercise the chart's tri-mode database wiring:

  postgres.subchart.enabled=true  (default) → CloudNativePG Cluster CRD +
                                              helper-derived DSN env + creds Secret
  postgres.subchart.enabled=false +
    postgres.external.dsn=...            → DSN value injected into env directly
  postgres.subchart.enabled=false +
    postgres.external.dsn empty          → legacy secretKeyRef behavior (backward compat)

We invoke ``helm template`` as a subprocess and parse the rendered YAML so
the assertions are exactly what an operator's ``helm install`` would see.
"""

from __future__ import annotations

import os
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
    assert result.returncode == 0, (
        f"helm template failed: {result.stderr}\nstdout-tail: {result.stdout[-500:]}"
    )
    return [doc for doc in yaml.safe_load_all(result.stdout) if doc]


def _by_kind_and_name(docs: list[dict], kind: str, name: str) -> dict | None:
    for d in docs:
        if d.get("kind") == kind and d.get("metadata", {}).get("name") == name:
            return d
    return None


def _kinds(docs: list[dict]) -> list[str]:
    return [d.get("kind", "") for d in docs]


# -------------------- vanilla install (subcharts enabled) --------------------


def test_vanilla_install_renders_postgres_cluster_crd_instance():
    docs = _render(release="tst")
    cluster = _by_kind_and_name(docs, "Cluster", "tst-omnix-postgres")
    assert cluster is not None, "Cluster CRD instance for postgres not rendered"
    assert cluster["spec"]["instances"] == 2
    assert cluster["spec"]["bootstrap"]["initdb"]["database"] == "omnix"


def test_vanilla_install_renders_postgres_creds_secret():
    docs = _render(release="tst")
    sec = _by_kind_and_name(docs, "Secret", "tst-omnix-postgres-creds")
    assert sec is not None
    assert sec["stringData"]["username"] == "omnix"
    assert sec["stringData"]["password"]  # auto-generated, non-empty


def test_vanilla_install_renders_minio_pod():
    docs = _render(release="tst")
    # Bitnami subchart names the pod controller deterministically.
    # Either Deployment or StatefulSet depending on chart version; assert
    # the kinds list contains a minio-flavored workload.
    minio_kinds = [d for d in docs if "minio" in (d.get("metadata", {}).get("name") or "").lower()]
    assert minio_kinds, f"no minio resources in render. Kinds: {_kinds(docs)}"


def test_vanilla_install_api_env_uses_helper_dsn_not_secret():
    docs = _render(release="tst")
    api = _by_kind_and_name(docs, "Deployment", "tst-omnix-api")
    assert api is not None
    env = api["spec"]["template"]["spec"]["containers"][0]["env"]
    dsn_envs = [e for e in env if e["name"] == "OMNIX_DATABASE_URL"]
    assert len(dsn_envs) == 1
    # Subchart mode populates a literal value (helper output), not a secretKeyRef.
    assert "value" in dsn_envs[0]
    assert "valueFrom" not in dsn_envs[0]
    assert "tst-omnix-postgres-rw" in dsn_envs[0]["value"]


def test_vanilla_install_api_env_has_postgres_password_from_creds_secret():
    docs = _render(release="tst")
    api = _by_kind_and_name(docs, "Deployment", "tst-omnix-api")
    env = api["spec"]["template"]["spec"]["containers"][0]["env"]
    pw_envs = [e for e in env if e["name"] == "POSTGRES_PASSWORD"]
    assert len(pw_envs) == 1
    sec_ref = pw_envs[0]["valueFrom"]["secretKeyRef"]
    assert sec_ref["name"] == "tst-omnix-postgres-creds"
    assert sec_ref["key"] == "password"


def test_vanilla_install_worker_env_also_uses_helper_dsn():
    docs = _render(release="tst")
    worker = _by_kind_and_name(docs, "Deployment", "tst-omnix-worker")
    assert worker is not None
    env = worker["spec"]["template"]["spec"]["containers"][0]["env"]
    dsn_envs = [e for e in env if e["name"] == "OMNIX_DATABASE_URL"]
    assert len(dsn_envs) == 1
    assert "value" in dsn_envs[0]
    assert "tst-omnix-postgres-rw" in dsn_envs[0]["value"]


# -------------------- external DSN mode (production) -------------------------


def test_external_dsn_skips_postgres_cluster_crd():
    docs = _render(
        "postgres.subchart.enabled=false",
        "postgres.external.dsn=postgres://prod.example:5432/omnix",
    )
    assert _by_kind_and_name(docs, "Cluster", "tst-omnix-postgres") is None
    assert _by_kind_and_name(docs, "Secret", "tst-omnix-postgres-creds") is None


def test_external_dsn_renders_dsn_directly_in_api_env():
    docs = _render(
        "postgres.subchart.enabled=false",
        "postgres.external.dsn=postgres://prod.example:5432/omnix",
    )
    api = _by_kind_and_name(docs, "Deployment", "tst-omnix-api")
    env = api["spec"]["template"]["spec"]["containers"][0]["env"]
    dsn_envs = [e for e in env if e["name"] == "OMNIX_DATABASE_URL"]
    assert len(dsn_envs) == 1
    assert dsn_envs[0]["value"] == "postgres://prod.example:5432/omnix"
    # Should not also be setting POSTGRES_PASSWORD (no managed creds).
    assert not any(e["name"] == "POSTGRES_PASSWORD" for e in env)


# -------------------- legacy mode (subchart off, no external) ---------------


def test_legacy_mode_falls_back_to_secret_keyref():
    docs = _render("postgres.subchart.enabled=false")
    api = _by_kind_and_name(docs, "Deployment", "tst-omnix-api")
    env = api["spec"]["template"]["spec"]["containers"][0]["env"]
    dsn_envs = [e for e in env if e["name"] == "OMNIX_DATABASE_URL"]
    assert len(dsn_envs) == 1
    assert "valueFrom" in dsn_envs[0]
    assert dsn_envs[0]["valueFrom"]["secretKeyRef"]["name"] == "omnix-db-dsn"


# -------------------- MinIO toggle --------------------


def test_minio_subchart_disabled_omits_minio_resources():
    docs = _render("minio.subchart.enabled=false")
    minio_names = [
        d.get("metadata", {}).get("name", "")
        for d in docs
        if "minio" in (d.get("metadata", {}).get("name") or "").lower()
    ]
    assert minio_names == [], f"expected no minio resources, got: {minio_names}"


# -------------------- helper definitions render ------------------------------


def test_postgres_dsn_helper_is_invoked_for_subchart_mode():
    """When postgres.subchart.enabled=true, the rendered DSN must reference
    the in-cluster CNPG -rw service (the helper's subchart branch)."""
    docs = _render(release="z9")
    api = _by_kind_and_name(docs, "Deployment", "z9-omnix-api")
    env = api["spec"]["template"]["spec"]["containers"][0]["env"]
    dsn = next(e for e in env if e["name"] == "OMNIX_DATABASE_URL")
    # The helper interpolates the release name into the -rw service name.
    assert "z9-omnix-postgres-rw" in dsn["value"]
    # Uses asyncpg driver per the helper.
    assert dsn["value"].startswith("postgresql+asyncpg://")


def test_postgres_dsn_helper_external_wins_over_subchart():
    """Even with subchart.enabled=true, an explicit external.dsn wins.

    Review finding M2: when external.dsn is set the env must NOT also
    inject POSTGRES_PASSWORD from the subchart secret (it's irrelevant
    and the external DSN doesn't carry a $(POSTGRES_PASSWORD) variable).
    """
    docs = _render(
        "postgres.external.dsn=postgres://override.example/db",
    )
    api = _by_kind_and_name(docs, "Deployment", "tst-omnix-api")
    env = api["spec"]["template"]["spec"]["containers"][0]["env"]
    dsn_envs = [e for e in env if e["name"] == "OMNIX_DATABASE_URL"]
    assert any(e.get("value") == "postgres://override.example/db" for e in dsn_envs)
    # No POSTGRES_PASSWORD when external DSN is in play.
    assert not any(e["name"] == "POSTGRES_PASSWORD" for e in env), (
        "external.dsn must not co-inject POSTGRES_PASSWORD from subchart secret"
    )
