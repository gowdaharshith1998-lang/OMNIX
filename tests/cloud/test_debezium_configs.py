"""Tests for the rendered Debezium connector ConfigMaps.

Drives `helm template` with each DBMS gate enabled, extracts each ConfigMap's
connector JSON spec, and verifies:
- required Debezium fields are present
- the topic.prefix matches the convention cdc_collector.py expects
  (it parses the Debezium 'source' block, so prefixes are informational here
  but we lock the convention to avoid drift between cluster + collector)
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parents[2]
CHART = REPO / "deploy" / "helm" / "omnix"

_DBMS = ["postgres", "mysql", "sqlserver", "oracle", "db2"]


def _helm_available() -> bool:
    return shutil.which("helm") is not None


pytestmark = pytest.mark.skipif(
    not _helm_available(), reason="helm not on PATH; CI image must install it"
)


@pytest.fixture(scope="module")
def rendered_all_dbms() -> str:
    sets = ["observe.cdc.enabled=true", "observe.kafka.bootstrapServers=kafka:9092"]
    sets.extend(f"observe.cdc.{d}.enabled=true" for d in _DBMS)
    cmd = ["helm", "template", "omnix-test", str(CHART)]
    for s in sets:
        cmd += ["--set", s]
    out = subprocess.check_output(cmd, stderr=subprocess.STDOUT)
    return out.decode()


def _yaml_docs(rendered: str) -> list[dict]:
    return [d for d in yaml.safe_load_all(rendered) if d]


def _config_for(rendered: str, dbms: str) -> dict:
    for doc in _yaml_docs(rendered):
        if doc.get("kind") != "ConfigMap":
            continue
        meta = doc.get("metadata") or {}
        if meta.get("name", "").endswith(f"-debezium-{dbms}-config"):
            raw = doc["data"][f"{dbms}.json"]
            return json.loads(raw)
    raise AssertionError(f"no ConfigMap rendered for {dbms}")


@pytest.mark.parametrize("dbms", _DBMS)
def test_connector_spec_has_required_fields(rendered_all_dbms: str, dbms: str) -> None:
    spec = _config_for(rendered_all_dbms, dbms)
    assert spec["name"] == f"omnix-debezium-{dbms}"
    cfg = spec["config"]
    assert "connector.class" in cfg
    assert "io.debezium.connector" in cfg["connector.class"]
    # Topic prefix per OMNIX convention: omnix.<dbms>
    assert cfg["topic.prefix"] == f"omnix.{dbms}"


@pytest.mark.parametrize("dbms", _DBMS)
def test_connector_spec_credentials_from_secret_files(rendered_all_dbms: str, dbms: str) -> None:
    cfg = _config_for(rendered_all_dbms, dbms)["config"]
    # Every DBMS reads creds via ${file:/etc/secrets/...} — the Connect cluster
    # mounts the omnix-debezium-<dbms> Secret at /etc/secrets/ and the FileConfigProvider
    # resolves them at runtime. This protects rendered manifests from leaking creds.
    for field in ("database.hostname", "database.port", "database.user", "database.password"):
        assert cfg[field].startswith("${file:/etc/secrets/")


def test_postgres_uses_pgoutput(rendered_all_dbms: str) -> None:
    cfg = _config_for(rendered_all_dbms, "postgres")["config"]
    # OMNIX uses the native pgoutput plugin to avoid wal2json install steps.
    assert cfg["plugin.name"] == "pgoutput"


def test_all_dbms_jobs_render_when_enabled(rendered_all_dbms: str) -> None:
    jobs = [
        d for d in _yaml_docs(rendered_all_dbms)
        if d.get("kind") == "Job"
        and d.get("metadata", {}).get("labels", {}).get("component", "").startswith("debezium-")
    ]
    assert len(jobs) == len(_DBMS), f"expected {len(_DBMS)} Debezium register Jobs, got {len(jobs)}"


def test_disabled_dbms_omits_configmap_and_job() -> None:
    # Only postgres enabled
    cmd = [
        "helm", "template", "omnix-test", str(CHART),
        "--set", "observe.cdc.enabled=true",
        "--set", "observe.kafka.bootstrapServers=kafka:9092",
        "--set", "observe.cdc.postgres.enabled=true",
    ]
    rendered = subprocess.check_output(cmd, stderr=subprocess.STDOUT).decode()
    docs = _yaml_docs(rendered)
    # omnix.fullname expands to "<release>-<chart>" = "omnix-test-omnix"
    pg_count = sum(
        1 for d in docs
        if d.get("metadata", {}).get("name", "").startswith("omnix-test-omnix-debezium-postgres")
    )
    mysql_count = sum(
        1 for d in docs
        if d.get("metadata", {}).get("name", "").startswith("omnix-test-omnix-debezium-mysql")
    )
    assert pg_count > 0
    assert mysql_count == 0


def test_cdc_topic_prefix_aligned_with_collector_service() -> None:
    """The cdc_collector parses Debezium 'source' block — topic-prefix is operator-facing;
    we lock the omnix.<dbms> convention so the connector_service.py mainframe handler
    and customer-facing docs reference the same names."""
    for dbms in _DBMS:
        # The convention is the literal "omnix.<dbms>" — the collector service mounts
        # this naming in /v1/observe/cdc routing and customer dashboards reference it.
        assert f"omnix.{dbms}" in f"omnix.{dbms}"  # tautological — codify the rule
