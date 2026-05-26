"""P6 — values.schema.json validation tests.

Two layers:

1. Direct jsonschema validation of the published schema against a
   constructed values dict — catches schema/values drift at unit-test
   speed without invoking helm.

2. `helm template --set ...=BAD-VALUE` invocations confirm helm's own
   built-in schema check returns the expected error to operators.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

CHART_DIR = Path(__file__).resolve().parents[2] / "deploy" / "helm" / "omnix"
SCHEMA_PATH = CHART_DIR / "values.schema.json"

pytestmark = pytest.mark.skipif(
    not SCHEMA_PATH.exists(), reason="values.schema.json missing"
)


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _validate(values: dict) -> list[str]:
    """Returns a list of jsonschema error messages (empty when valid)."""
    import jsonschema
    errors = sorted(
        jsonschema.Draft7Validator(_schema()).iter_errors(values),
        key=lambda e: list(e.path),
    )
    return [f"{'.'.join(str(p) for p in e.path)}: {e.message}" for e in errors]


def _default_values() -> dict:
    """Minimal shape that passes the schema — matches the chart's defaults."""
    return {
        "global": {"image": {"registry": "ghcr.io/x", "pullPolicy": "IfNotPresent"}},
        "api": {"enabled": True, "replicaCount": 2,
                "env": {"OMNIX_STORAGE_BACKEND": "minio"}},
        "worker": {"enabled": True, "replicaCount": 4},
        "studio": {"enabled": True, "replicaCount": 2},
        "verifier": {"enabled": True, "replicaCount": 2},
        "networkPolicy": {"enabled": True, "denyAll": False,
                          "allowSameNamespace": True},
        "postgres": {"enabled": True,
                     "subchart": {"enabled": True, "replicas": 2},
                     "external": {"dsn": ""}},
        "minio": {"subchart": {"enabled": True}},
        "facade": {"enabled": False, "envoyImage": "envoyproxy/envoy:v1.32.0",
                   "replicas": 1, "legacyService": "",
                   "candidateServiceTemplate": ""},
        "ebpf": {"tetragon": {"enabled": False}},
        "observe": {"collector": {"enabled": False, "sink": "memory"}},
        "mainframe": {"enabled": False},
        "rekor": {"enabled": False},
    }


# -------------------- direct schema validation ------------------------------


def test_schema_loads_as_valid_draft7():
    import jsonschema
    schema = _schema()
    # validates the schema document itself against Draft-07 meta-schema
    jsonschema.Draft7Validator.check_schema(schema)


def test_schema_accepts_default_values():
    assert _validate(_default_values()) == []


def test_schema_rejects_invalid_storage_backend():
    v = _default_values()
    v["api"]["env"]["OMNIX_STORAGE_BACKEND"] = "yolo"
    errors = _validate(v)
    assert any("OMNIX_STORAGE_BACKEND" in e for e in errors), errors


def test_schema_accepts_each_supported_storage_backend():
    for backend in ("minio", "s3", "r2", "memory"):
        v = _default_values()
        v["api"]["env"]["OMNIX_STORAGE_BACKEND"] = backend
        assert _validate(v) == [], f"backend={backend!r} rejected"


def test_schema_rejects_facade_enabled_without_unit_placeholder():
    v = _default_values()
    v["facade"]["enabled"] = True
    v["facade"]["legacyService"] = "legacy.svc:80"
    v["facade"]["candidateServiceTemplate"] = "candidate-no-placeholder"
    errors = _validate(v)
    assert any("candidateServiceTemplate" in e for e in errors), errors


def test_schema_accepts_facade_enabled_with_unit_placeholder():
    v = _default_values()
    v["facade"]["enabled"] = True
    v["facade"]["legacyService"] = "legacy.svc:80"
    v["facade"]["candidateServiceTemplate"] = "candidate_{unit}.svc"
    assert _validate(v) == []


def test_schema_rejects_postgres_replicas_out_of_range():
    v = _default_values()
    v["postgres"]["subchart"]["replicas"] = 99
    errors = _validate(v)
    assert any("replicas" in e for e in errors), errors


def test_schema_rejects_observe_collector_sink_enum():
    v = _default_values()
    v["observe"]["collector"]["sink"] = "kafka"
    errors = _validate(v)
    assert any("sink" in e for e in errors), errors


def test_schema_rejects_negative_replica_count_on_api():
    v = _default_values()
    v["api"]["replicaCount"] = 0
    errors = _validate(v)
    assert any("replicaCount" in e for e in errors), errors


# -------------------- helm's built-in schema check --------------------------


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm CLI not on PATH")
def test_helm_template_rejects_bad_storage_backend():
    result = subprocess.run(
        ["helm", "template", "t", str(CHART_DIR),
         "--set", "api.env.OMNIX_STORAGE_BACKEND=yolo"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "OMNIX_STORAGE_BACKEND" in result.stderr
    assert "must be one of" in result.stderr


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm CLI not on PATH")
def test_helm_template_rejects_facade_enabled_without_placeholder():
    result = subprocess.run(
        ["helm", "template", "t", str(CHART_DIR),
         "--set", "facade.enabled=true",
         "--set", "facade.legacyService=legacy:80",
         "--set", "facade.candidateServiceTemplate=no-placeholder"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "candidateServiceTemplate" in result.stderr


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm CLI not on PATH")
def test_helm_template_accepts_default_values():
    result = subprocess.run(
        ["helm", "template", "t", str(CHART_DIR)],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, f"helm template failed: {result.stderr}"


# -------------------- helm test hook smoke pod renders ----------------------


@pytest.mark.skipif(shutil.which("helm") is None, reason="helm CLI not on PATH")
def test_helm_template_renders_smoke_test_pod():
    result = subprocess.run(
        ["helm", "template", "t", str(CHART_DIR),
         "--show-only", "templates/tests/test-smoke.yaml"],
        capture_output=True, text=True,
    )
    assert result.returncode == 0, result.stderr
    assert "kind: Pod" in result.stdout
    # Helm template emits the annotation with quoted key+value; both forms
    # are valid YAML so we match either.
    assert ('"helm.sh/hook": test' in result.stdout
            or "helm.sh/hook: test" in result.stdout), result.stdout
    assert "smoke-test" in result.stdout
