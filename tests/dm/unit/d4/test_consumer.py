"""Tests for the PR C consumer (loads + verifies the PR A+B Merkle chain)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm.d4_bulk_import.consumer import (
    InconsistentReceiptStateError,
    PrePhaseSignatureError,
    load_prior_receipts,
)
from omnix.dm.receipts.ml_dsa_65_signer import canonicalize, sign_canonical


def _d1_payload(migration_id="m1") -> dict:
    return {
        "schema_version": "omnix-dm/column-mapping/v1",
        "migration_id": migration_id,
        "timestamp": "2026-05-27T00:00:00+00:00",
        "legacy_schema": {
            "dialect": "postgres",
            "name": "legacy",
            "tables": [
                {
                    "name": "owners",
                    "columns": [
                        {
                            "name": "email",
                            "raw_type": "VARCHAR(100)",
                            "normalized_type": "STRING",
                            "nullable": True,
                            "default": None,
                            "primary_key": False,
                            "unique": False,
                            "comment": None,
                            "dialect_specific": {},
                        }
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
                        }
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
        "public_key_fingerprint": "deadbeef",
        "requires_operator_review": False,
    }


def _d2_payload(migration_id="m1") -> dict:
    return {
        "schema_version": "omnix-dm/edge-case-manifest/v1",
        "migration_id": migration_id,
        "timestamp": "2026-05-27T00:00:00+00:00",
        "predecessor_hash": "ab" * 32,
        "findings": [],
        "probe_failures": [],
        "requires_operator_review": False,
        "stats": {
            "total_probes_run": 1,
            "total_findings": 0,
            "blocker_count": 0,
            "warn_count": 0,
            "info_count": 0,
            "timeout_count": 0,
            "error_count": 0,
        },
        "signing_algorithm": "ML-DSA-65",
        "public_key_fingerprint": "deadbeef",
    }


def _spec_payload(key="owners.email") -> dict:
    return {
        "schema_version": "omnix-dm/transformer-spec/v1",
        "migration_id": "m1",
        "timestamp": "2026-05-27T00:00:00+00:00",
        "predecessor_hash": hashlib.sha256(b"d2").hexdigest(),
        "column_mapping_key": key,
        "python_source": "def transform(v):\n    return v\n",
        "sql_case": None,
        "datalog_rule": None,
        "properties_passed": ["type_preservation"],
        "properties_failed": [],
        "mfi_history": [],
        "iterations_used": 1,
        "cegis_pruned_sketches": [],
        "tier_failures": [],
        "tier_chosen": "python",
        "confidence": 0.95,
        "requires_operator_review": False,
        "bisimulation_placeholder": {},
        "signing_algorithm": "ML-DSA-65",
        "public_key_fingerprint": "deadbeef",
    }


def _write_pra(root: Path, keys=None):
    pra = root / "pra-d1-d2" / "m1"
    pra.mkdir(parents=True)
    d1 = _d1_payload()
    d2 = _d2_payload()
    if keys is not None:
        _, sk = keys
        c1, sig1 = sign_canonical(d1, sk)
        c2, sig2 = sign_canonical(d2, sk)
        (pra / "column-mapping.json").write_bytes(c1)
        (pra / "edge-case-manifest.json").write_bytes(c2)
        (pra / "column-mapping.json.sig").write_text(sig1)
        (pra / "edge-case-manifest.json.sig").write_text(sig2)
    else:
        (pra / "column-mapping.json").write_text(json.dumps(d1, sort_keys=True, separators=(",", ":")))
        (pra / "edge-case-manifest.json").write_text(json.dumps(d2, sort_keys=True, separators=(",", ":")))


def _write_prb(root: Path, *, with_spec=True, with_halt=False, keys=None):
    prb = root / "prb-d3" / "m1"
    prb.mkdir(parents=True)
    if with_spec:
        spec = _spec_payload()
        if keys is not None:
            _, sk = keys
            c, sig = sign_canonical(spec, sk)
            (prb / "transformer-spec-owners.email.json").write_bytes(c)
            (prb / "transformer-spec-owners.email.json.sig").write_text(sig)
        else:
            (prb / "transformer-spec-owners.email.json").write_text(
                json.dumps(spec, sort_keys=True, separators=(",", ":"))
            )
    if with_halt:
        halt = {
            "schema_version": "omnix-dm/transformer-halt/v1",
            "migration_id": "m1",
            "timestamp": "2026-05-27T00:00:00+00:00",
            "predecessor_hash": hashlib.sha256(b"d2").hexdigest(),
            "column_mapping_key": "owners.email",
            "halt_reason": "iteration_cap",
            "latest_python_source": "",
            "failing_mfis": [],
            "last_critique": "",
            "iterations_used": 5,
            "security_violation": None,
            "signing_algorithm": "ML-DSA-65",
            "public_key_fingerprint": "deadbeef",
        }
        if keys is not None:
            _, sk = keys
            c, sig = sign_canonical(halt, sk)
            (prb / "transformer-halt-owners.email.json").write_bytes(c)
            (prb / "transformer-halt-owners.email.json.sig").write_text(sig)
        else:
            (prb / "transformer-halt-owners.email.json").write_text(
                json.dumps(halt, sort_keys=True, separators=(",", ":"))
            )


def test_happy_path_without_signatures(tmp_path: Path):
    _write_pra(tmp_path)
    _write_prb(tmp_path, with_spec=True)
    bundle = load_prior_receipts("m1", receipts_root=tmp_path, verify_signatures=False)
    assert len(bundle.column_mappings) == 1
    assert "owners.email" in bundle.transformer_specs
    assert len(bundle.predecessor_hash) == 64
    assert bundle.unmapped_columns == ()


def test_happy_path_with_signature_verification(tmp_path: Path):
    keys = ml_dsa_65.keypair(seed=b"\x11" * 48)
    pk, _ = keys
    _write_pra(tmp_path, keys=keys)
    _write_prb(tmp_path, with_spec=True, keys=keys)
    bundle = load_prior_receipts(
        "m1", receipts_root=tmp_path, public_key=pk, verify_signatures=True
    )
    assert "owners.email" in bundle.transformer_specs


def test_missing_pra_raises_file_not_found(tmp_path: Path):
    with pytest.raises(FileNotFoundError):
        load_prior_receipts("m1", receipts_root=tmp_path, verify_signatures=False)


def test_corrupted_signature_raises(tmp_path: Path):
    keys = ml_dsa_65.keypair(seed=b"\x11" * 48)
    pk, _ = keys
    _write_pra(tmp_path, keys=keys)
    (tmp_path / "pra-d1-d2" / "m1" / "column-mapping.json.sig").write_text("00" * 3309)
    with pytest.raises(PrePhaseSignatureError):
        load_prior_receipts(
            "m1", receipts_root=tmp_path, public_key=pk, verify_signatures=True
        )


def test_column_with_both_spec_and_halt_raises(tmp_path: Path):
    _write_pra(tmp_path)
    _write_prb(tmp_path, with_spec=True, with_halt=True)
    with pytest.raises(InconsistentReceiptStateError):
        load_prior_receipts("m1", receipts_root=tmp_path, verify_signatures=False)


def test_column_with_neither_recorded_in_unmapped(tmp_path: Path):
    _write_pra(tmp_path)
    (tmp_path / "prb-d3" / "m1").mkdir(parents=True)  # empty
    bundle = load_prior_receipts("m1", receipts_root=tmp_path, verify_signatures=False)
    assert bundle.unmapped_columns == ("owners.email",)
