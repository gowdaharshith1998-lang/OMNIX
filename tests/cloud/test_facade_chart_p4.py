"""P4 — static-mode fallback path tests (issue #53 dispatch).

The static-clusters helper and bootstrap branch were added in P2; this
file adds the schema-enforcement tests that prove mode=static requires
non-empty staticUnits, plus structural assertions on N-unit renders.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml

CHART_DIR = Path(__file__).resolve().parents[2] / "deploy" / "helm" / "omnix"
SCHEMA_PATH = CHART_DIR / "values.schema.json"

pytestmark = pytest.mark.skipif(
    shutil.which("helm") is None, reason="helm CLI not on PATH"
)


def _schema() -> dict:
    return json.loads(SCHEMA_PATH.read_text())


def _validate(values: dict) -> list[str]:
    import jsonschema
    errors = sorted(
        jsonschema.Draft7Validator(_schema()).iter_errors(values),
        key=lambda e: list(e.path),
    )
    return [f"{'.'.join(str(p) for p in e.path)}: {e.message}" for e in errors]


def _facade(values: dict) -> dict:
    return {
        "global": {"image": {"registry": "x", "pullPolicy": "IfNotPresent"}},
        "api": {"enabled": True, "replicaCount": 1,
                "env": {"OMNIX_STORAGE_BACKEND": "minio"}},
        "worker": {"enabled": True, "replicaCount": 1},
        "studio": {"enabled": True, "replicaCount": 1},
        "verifier": {"enabled": True, "replicaCount": 1},
        "networkPolicy": {"enabled": True, "denyAll": False, "allowSameNamespace": True},
        "postgres": {"enabled": True, "subchart": {"enabled": True, "replicas": 2},
                     "external": {"dsn": ""}},
        "minio": {"subchart": {"enabled": True}},
        "ebpf": {"tetragon": {"enabled": False}},
        "observe": {"collector": {"enabled": False, "sink": "memory"}},
        "mainframe": {"enabled": False},
        "rekor": {"enabled": False},
        "facade": values,
    }


# -------------------- Schema enforcement --------------------


def test_schema_rejects_static_mode_with_empty_units():
    """Critical: static-mode without units would render an empty cluster list
    and Envoy would 503 every request. Schema must catch this at install time.
    """
    v = _facade({
        "enabled": True,
        "mode": "static",
        "staticUnits": [],
        "legacyService": "legacy:80",
        "candidateServiceTemplate": "cand-{unit}:80",
    })
    errors = _validate(v)
    assert any("staticUnits" in e for e in errors), errors


def test_schema_rejects_static_mode_without_units_field():
    v = _facade({
        "enabled": True,
        "mode": "static",
        "legacyService": "legacy:80",
        "candidateServiceTemplate": "cand-{unit}:80",
    })
    errors = _validate(v)
    assert any("staticUnits" in e for e in errors), errors


def test_schema_accepts_static_mode_with_units_list():
    v = _facade({
        "enabled": True,
        "mode": "static",
        "staticUnits": ["calculator", "payments"],
        "legacyService": "legacy:80",
        "candidateServiceTemplate": "cand-{unit}:80",
    })
    assert _validate(v) == []


def test_schema_accepts_dynamic_mode_without_units():
    v = _facade({
        "enabled": True,
        "mode": "dynamic",
        "legacyService": "legacy:80",
        "candidateServiceTemplate": "cand-{unit}:80",
    })
    assert _validate(v) == []


def test_schema_rejects_mode_outside_enum():
    v = _facade({
        "enabled": True,
        "mode": "turbo",
        "legacyService": "legacy:80",
        "candidateServiceTemplate": "cand-{unit}:80",
    })
    errors = _validate(v)
    assert any("mode" in e for e in errors), errors


def test_schema_rejects_unit_name_with_underscore_or_caps():
    """Unit names become Kubernetes Service / Deployment names — must match
    the DNS-1123 label subset.
    """
    v = _facade({
        "enabled": True,
        "mode": "static",
        "staticUnits": ["Bad_Name"],
        "legacyService": "legacy:80",
        "candidateServiceTemplate": "cand-{unit}:80",
    })
    errors = _validate(v)
    assert any("staticUnits" in e for e in errors), errors


def test_schema_accepts_well_formed_unit_names():
    for name in ("calc", "payments", "user-auth", "v2-handler", "a", "x9"):
        v = _facade({
            "enabled": True, "mode": "static", "staticUnits": [name],
            "legacyService": "l:80", "candidateServiceTemplate": "c-{unit}:80",
        })
        assert _validate(v) == [], f"valid unit name rejected: {name!r}"


# -------------------- Structural renders --------------------


def _render(*set_args: str) -> list[dict]:
    cmd = ["helm", "template", "tst", str(CHART_DIR)]
    for s in set_args:
        cmd += ["--set", s]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False)
    assert result.returncode == 0, f"helm template failed: {result.stderr}"
    return [d for d in yaml.safe_load_all(result.stdout) if d]


def _envoy_bootstrap(docs: list[dict]) -> dict:
    cm = next(d for d in docs if d.get("kind") == "ConfigMap"
              and "facade-envoy" in d.get("metadata", {}).get("name", ""))
    return yaml.safe_load(cm["data"]["envoy.yaml"])


def test_static_mode_with_3_units_emits_6_clusters():
    docs = _render(
        "facade.enabled=true",
        "facade.mode=static",
        "facade.staticUnits={calculator,payments,auth}",
        "facade.legacyService=legacy:80",
        "facade.candidateServiceTemplate=cand-{unit}:80",
    )
    bootstrap = _envoy_bootstrap(docs)
    clusters = bootstrap["static_resources"]["clusters"]
    assert len(clusters) == 6  # 3 legacy + 3 candidate


def test_static_mode_with_1_unit_emits_2_clusters():
    docs = _render(
        "facade.enabled=true",
        "facade.mode=static",
        "facade.staticUnits={solo}",
        "facade.legacyService=legacy:80",
        "facade.candidateServiceTemplate=cand-{unit}:80",
    )
    bootstrap = _envoy_bootstrap(docs)
    clusters = bootstrap["static_resources"]["clusters"]
    names = {c["name"] for c in clusters}
    assert names == {"legacy_solo", "candidate_solo"}


def test_helm_install_fails_loud_when_static_mode_has_no_units():
    """helm's built-in schema validator catches the error before any
    template rendering — operator sees the constraint, not a cryptic
    Envoy 503 later.
    """
    result = subprocess.run(
        ["helm", "template", "tst", str(CHART_DIR),
         "--set", "facade.enabled=true",
         "--set", "facade.mode=static",
         "--set", "facade.legacyService=l:80",
         "--set", "facade.candidateServiceTemplate=c-{unit}:80"],
        capture_output=True, text=True,
    )
    assert result.returncode != 0
    assert "staticUnits" in result.stderr
