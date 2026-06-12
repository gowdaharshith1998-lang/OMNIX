"""Tests for the PR A manifest consumer (P10)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm.d3_transformation_synthesis.consumer import (
    ConsumerHalt,
    load_manifests,
)
from omnix.dm.receipts.ml_dsa_65_signer import sign_canonical


def _make_d1(migration_id="m1") -> dict:
    return {
        "schema_version": "omnix-dm/column-mapping/v1",
        "migration_id": migration_id,
        "timestamp": "2026-05-26T00:00:00+00:00",
        "legacy_schema": {
            "dialect": "oracle",
            "name": "legacy",
            "tables": [
                {
                    "name": "owners",
                    "columns": [
                        {
                            "name": "email",
                            "raw_type": "VARCHAR2(100)",
                            "normalized_type": "STRING",
                            "nullable": True,
                            "default": None,
                            "primary_key": False,
                            "unique": False,
                            "comment": None,
                            "dialect_specific": {},
                        },
                    ],
                    "primary_key": [],
                    "foreign_keys": [],
                    "indexes": [],
                    "comment": None,
                }
            ],
            "parse_warnings": [],
        },
        "target_schema": {
            "dialect": "postgres",
            "name": "target",
            "tables": [
                {
                    "name": "owners",
                    "columns": [
                        {
                            "name": "email",
                            "raw_type": "TEXT",
                            "normalized_type": "TEXT",
                            "nullable": True,
                            "default": None,
                            "primary_key": False,
                            "unique": False,
                            "comment": None,
                            "dialect_specific": {},
                        },
                    ],
                    "primary_key": [],
                    "foreign_keys": [],
                    "indexes": [],
                    "comment": None,
                }
            ],
            "parse_warnings": [],
        },
        "mappings": [
            {
                "legacy_table": "owners",
                "legacy_column": "email",
                "target_table": "owners",
                "target_column": "email",
                "confidence": 0.95,
                "status": "ok",
                "candidates": [],
                "rationale": "exact match",
            }
        ],
        "predecessor_hash": None,
        "stats": {
            "total_legacy_columns": 1,
            "status_ok_count": 1,
            "status_low_confidence_count": 0,
            "status_ambiguous_count": 0,
            "status_no_match_count": 0,
        },
        "signing_algorithm": "ML-DSA-65",
        "public_key_fingerprint": "deadbeefdeadbeef",
        "requires_operator_review": False,
    }


def _make_d2(predecessor_hash="abcd" * 16) -> dict:
    return {
        "schema_version": "omnix-dm/edge-case-manifest/v1",
        "migration_id": "m1",
        "timestamp": "2026-05-26T00:00:00+00:00",
        "predecessor_hash": predecessor_hash,
        "findings": [
            {
                "probe_category": "encoding_anomaly",
                "legacy_table": "owners",
                "legacy_column": "email",
                "anomaly_type": "mojibake",
                "severity": "blocker",
                "sample_values": ["café"],
                "affected_row_count": 5,
                "remediation_hint": "normalize via re.sub",
                "requires_human_decision": True,
            }
        ],
        "probe_failures": [],
        "requires_operator_review": True,
        "stats": {
            "total_probes_run": 1,
            "total_findings": 1,
            "blocker_count": 1,
            "warn_count": 0,
            "info_count": 0,
            "timeout_count": 0,
            "error_count": 0,
        },
        "signing_algorithm": "ML-DSA-65",
        "public_key_fingerprint": "deadbeefdeadbeef",
    }


def _write_manifests(tmp_path: Path, *, sign=False, keys=None):
    base = tmp_path / "m1"
    base.mkdir()
    d1 = _make_d1()
    d2 = _make_d2()
    (base / "column-mapping.json").write_text(json.dumps(d1, sort_keys=True, separators=(",", ":")))
    (base / "edge-case-manifest.json").write_text(
        json.dumps(d2, sort_keys=True, separators=(",", ":"))
    )
    if sign:
        pk, sk = keys
        _, sig1 = sign_canonical(d1, sk)
        _, sig2 = sign_canonical(d2, sk)
        (base / "column-mapping.json.sig").write_text(sig1)
        (base / "edge-case-manifest.json.sig").write_text(sig2)
    return tmp_path


def test_load_without_verification(tmp_path: Path):
    _write_manifests(tmp_path)
    out = load_manifests(tmp_path, "m1", verify_signatures=False)
    assert len(out.column_mappings) == 1
    assert out.column_mappings[0].legacy_column == "email"
    assert len(out.findings) == 1
    assert "owners.email" in out.column_specs
    assert "owners.email" in out.target_column_specs
    assert len(out.predecessor_hash) == 64


def test_signature_verification(tmp_path: Path):
    keys = ml_dsa_65.keypair(seed=b"\x33" * 48)
    pk, _sk = keys
    _write_manifests(tmp_path, sign=True, keys=keys)
    out = load_manifests(tmp_path, "m1", public_key=pk, verify_signatures=True)
    assert len(out.column_mappings) == 1


def test_bad_signature_raises_consumer_halt(tmp_path: Path):
    keys = ml_dsa_65.keypair(seed=b"\x33" * 48)
    pk, _sk = keys
    _write_manifests(tmp_path, sign=True, keys=keys)
    # Corrupt the signature.
    sig_path = tmp_path / "m1" / "column-mapping.json.sig"
    sig_path.write_text("00" * 3309)
    with pytest.raises(ConsumerHalt):
        load_manifests(tmp_path, "m1", public_key=pk, verify_signatures=True)


def test_verify_without_key_fails_closed(tmp_path: Path):
    """verify_signatures=True with no public_key must HALT, not silently skip."""
    _write_manifests(tmp_path, sign=True, keys=ml_dsa_65.keypair(seed=b"\x33" * 48))
    with pytest.raises(ConsumerHalt):
        load_manifests(tmp_path, "m1", public_key=None, verify_signatures=True)


def test_missing_manifest_raises_consumer_halt(tmp_path: Path):
    (tmp_path / "m1").mkdir()
    with pytest.raises(ConsumerHalt):
        load_manifests(tmp_path, "m1", verify_signatures=False)
