"""End-to-end PR B pipeline (mocked Claude).

Builds a synthetic Petclinic-shaped PR A output, runs every ColumnMapping
through the CEGIS + Reflexion loop with a deterministic mocked LLM, and
verifies receipts + Merkle chain integrity.

The pipeline exercises:
  * consumer.load_manifests (PR A consumption)
  * cegis.run_with_cegis (CEGIS + Reflexion)
  * spec_emitter.emit (TransformerSpec)
  * halt_report.emit_halt (HaltReport for the engineered-failure column)
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Dict, List

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm.d3_transformation_synthesis import (
    cegis,
    halt_report,
    llm_synthesizer,
    property_generator,
    spec_emitter,
)
from omnix.dm.d3_transformation_synthesis.consumer import findings_for, load_manifests
from omnix.dm.receipts import merkle_chain
from omnix.dm.receipts.ml_dsa_65_signer import canonicalize, sign_canonical

# ---------------------------------------------------------------------------
# Petclinic fixtures — 16 columns, one engineered failure
# ---------------------------------------------------------------------------


_PETCLINIC_TABLES = [
    (
        "owners",
        [
            ("id", "NUMBER", "INTEGER", False),
            ("first_name", "VARCHAR2(30)", "STRING", False),
            ("last_name", "VARCHAR2(30)", "STRING", False),
            ("email", "VARCHAR2(100)", "STRING", True),
            ("address", "VARCHAR2(255)", "STRING", True),
            ("city", "VARCHAR2(80)", "STRING", True),
            ("telephone", "VARCHAR2(20)", "STRING", True),
        ],
    ),
    (
        "pets",
        [
            ("id", "NUMBER", "INTEGER", False),
            ("name", "VARCHAR2(30)", "STRING", False),
            ("birth_date", "DATE", "DATE", True),
            ("type_id", "NUMBER", "INTEGER", False),
            ("owner_id", "NUMBER", "INTEGER", False),
        ],
    ),
    (
        "visits",
        [
            ("id", "NUMBER", "INTEGER", False),
            ("pet_id", "NUMBER", "INTEGER", False),
            ("visit_date", "DATE", "DATE", True),
            ("description", "VARCHAR2(255)", "STRING", True),
        ],
    ),
]


def _build_d1_manifest() -> dict:
    legacy_tables = []
    target_tables = []
    mappings = []
    for tname, cols in _PETCLINIC_TABLES:
        legacy_cols = []
        target_cols = []
        for cname, raw, norm, not_null in cols:
            legacy_cols.append(
                {
                    "name": cname,
                    "raw_type": raw,
                    "normalized_type": norm,
                    "nullable": not not_null,
                    "default": None,
                    "primary_key": False,
                    "unique": False,
                    "comment": None,
                    "dialect_specific": {},
                }
            )
            # PG side — most are STRING (TEXT) or INTEGER; birth_date promoted to TIMESTAMP_TZ.
            tgt_norm = norm
            tgt_raw = raw
            if norm == "DATE":
                tgt_norm = "TIMESTAMP_TZ"
                tgt_raw = "TIMESTAMP WITH TIME ZONE"
            elif norm == "STRING":
                tgt_norm = "STRING"
                tgt_raw = "TEXT"
            target_cols.append(
                {
                    "name": cname,
                    "raw_type": tgt_raw,
                    "normalized_type": tgt_norm,
                    "nullable": not not_null,
                    "default": None,
                    "primary_key": False,
                    "unique": False,
                    "comment": None,
                    "dialect_specific": {},
                }
            )
            mappings.append(
                {
                    "legacy_table": tname,
                    "legacy_column": cname,
                    "target_table": tname,
                    "target_column": cname,
                    "confidence": 0.94,
                    "status": "ok",
                    "candidates": [],
                    "rationale": "exact name + type match",
                }
            )
        legacy_tables.append(
            {
                "name": tname,
                "columns": legacy_cols,
                "primary_key": [],
                "foreign_keys": [],
                "indexes": [],
                "comment": None,
            }
        )
        target_tables.append(
            {
                "name": tname,
                "columns": target_cols,
                "primary_key": [],
                "foreign_keys": [],
                "indexes": [],
                "comment": None,
            }
        )
    return {
        "schema_version": "omnix-dm/column-mapping/v1",
        "migration_id": "petclinic-2026-05-26",
        "timestamp": "2026-05-26T00:00:00+00:00",
        "legacy_schema": {
            "dialect": "oracle",
            "name": "legacy",
            "tables": legacy_tables,
            "parse_warnings": [],
        },
        "target_schema": {
            "dialect": "postgres",
            "name": "target",
            "tables": target_tables,
            "parse_warnings": [],
        },
        "mappings": mappings,
        "predecessor_hash": None,
        "stats": {
            "total_legacy_columns": len(mappings),
            "status_ok_count": len(mappings),
            "status_low_confidence_count": 0,
            "status_ambiguous_count": 0,
            "status_no_match_count": 0,
        },
        "signing_algorithm": "ML-DSA-65",
        "public_key_fingerprint": "deadbeefdeadbeef",
        "requires_operator_review": False,
    }


def _build_d2_manifest(predecessor_hash: str = "ab" * 32) -> dict:
    findings = [
        {
            "probe_category": "encoding_anomaly",
            "legacy_table": "owners",
            "legacy_column": "first_name",
            "anomaly_type": "mojibake",
            "severity": "blocker",
            "sample_values": ["café", "naïve"],
            "affected_row_count": 12,
            "remediation_hint": "normalize encoding",
            "requires_human_decision": True,
        },
        {
            "probe_category": "timezone_drift",
            "legacy_table": "pets",
            "legacy_column": "birth_date",
            "anomaly_type": "timezone_dropped",
            "severity": "blocker",
            "sample_values": [],
            "affected_row_count": 5,
            "remediation_hint": "combine with UTC midnight",
            "requires_human_decision": True,
        },
        {
            "probe_category": "sentinel_value",
            "legacy_table": "owners",
            "legacy_column": "email",
            "anomaly_type": "sentinel_email",
            "severity": "blocker",
            "sample_values": ["N/A"],
            "affected_row_count": 8,
            "remediation_hint": "map sentinel to NULL",
            "requires_human_decision": True,
        },
    ]
    return {
        "schema_version": "omnix-dm/edge-case-manifest/v1",
        "migration_id": "petclinic-2026-05-26",
        "timestamp": "2026-05-26T00:00:00+00:00",
        "predecessor_hash": predecessor_hash,
        "findings": findings,
        "probe_failures": [],
        "requires_operator_review": True,
        "stats": {
            "total_probes_run": 3,
            "total_findings": 3,
            "blocker_count": 3,
            "warn_count": 0,
            "info_count": 0,
            "timeout_count": 0,
            "error_count": 0,
        },
        "signing_algorithm": "ML-DSA-65",
        "public_key_fingerprint": "deadbeefdeadbeef",
    }


def _write_pra_outputs(tmp_path: Path, keys) -> Path:
    pk, sk = keys
    root = tmp_path / "pra"
    base = root / "petclinic-2026-05-26"
    base.mkdir(parents=True)
    d1 = _build_d1_manifest()
    d2 = _build_d2_manifest(
        predecessor_hash=merkle_chain.next_hash(d1.get("predecessor_hash"), canonicalize(d1))
    )
    can1, sig1 = sign_canonical(d1, sk)
    can2, sig2 = sign_canonical(d2, sk)
    (base / "column-mapping.json").write_bytes(can1)
    (base / "column-mapping.json.sig").write_text(sig1)
    (base / "edge-case-manifest.json").write_bytes(can2)
    (base / "edge-case-manifest.json.sig").write_text(sig2)
    return root


# ---------------------------------------------------------------------------
# Mocked LLM backend — deterministic per-column responses
# ---------------------------------------------------------------------------


def _make_petclinic_backend(fail_column: str):
    """Return a backend that emits a working transformer for every column
    except ``fail_column``, where it emits a deliberately broken one so the
    Reflexion loop hits the iteration cap."""

    def _response_for(user_prompt: str) -> str:
        if f".{fail_column}" in user_prompt and "LEGACY COLUMN" in user_prompt:
            # broken: returns 9999 — type_preservation will fail on a STRING target
            return (
                "```python\ndef transform(v):\n    return 9999\n```\n"
                "```hypothesis\n# fail\n```\n"
            )
        # Heuristic per type pair — read from the LEGACY/TARGET TYPE lines.
        legacy_norm = "STRING"
        target_norm = "STRING"
        for line in user_prompt.splitlines():
            if line.startswith("LEGACY TYPE"):
                if "DATE" in line:
                    legacy_norm = "DATE"
                elif "INTEGER" in line or "NUMBER" in line:
                    legacy_norm = "INTEGER"
            if line.startswith("TARGET TYPE"):
                if "TIMESTAMP_TZ" in line or "TIMESTAMP WITH TIME ZONE" in line:
                    target_norm = "TIMESTAMP_TZ"
                elif "INTEGER" in line or "NUMBER" in line:
                    target_norm = "INTEGER"
        # Look for blocker categories in the prompt — they steer the transformer.
        has_encoding_blocker = '"category": "encoding_anomaly"' in user_prompt
        has_sentinel_blocker = '"category": "sentinel_value"' in user_prompt
        # Pick a transformer that satisfies the property generator's invariants.
        if legacy_norm == "DATE" and target_norm == "TIMESTAMP_TZ":
            py = (
                "def transform(v):\n"
                "    if v is None: return None\n"
                "    return datetime.datetime.combine(v, datetime.time.min, "
                "tzinfo=datetime.timezone.utc)\n"
            )
        elif target_norm == "INTEGER":
            py = "def transform(v):\n    return v if v is None else int(v)\n"
        elif has_encoding_blocker:
            py = (
                "def transform(v):\n"
                "    if v is None: return None\n"
                "    return v.strip() if isinstance(v, str) else v\n"
            )
        elif has_sentinel_blocker:
            py = (
                "def transform(v):\n"
                "    if v is None: return None\n"
                "    return None if v in ('N/A', 'NULL', 'TBD') else v\n"
            )
        else:
            # Passthrough — required to satisfy reversibility_when_lossless.
            py = "def transform(v):\n    return v\n"
        return (
            f"```python\n{py}\n```\n"
            "```hypothesis\n@given(st.text())\ndef test(v): pass\n```\n"
        )

    def _backend(sys_p, user_p, kw):
        return llm_synthesizer._BackendResponse(
            text=_response_for(user_p),
            model_id="mock-claude-opus-4-7",
            prompt_tokens=1,
            completion_tokens=1,
        )

    return _backend


# ---------------------------------------------------------------------------
# Integration test (marked opt-in)
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_backend():
    llm_synthesizer.set_llm_backend(None)
    yield
    llm_synthesizer.set_llm_backend(None)


def test_petclinic_end_to_end_with_mocked_llm(tmp_path: Path):
    """Run every Petclinic column through CEGIS+Reflexion (mocked LLM) and
    verify ≥15 specs + ≥1 halt + chain integrity."""
    keys = ml_dsa_65.keypair(seed=b"\x77" * 48)
    pk, sk = keys
    pra_root = _write_pra_outputs(tmp_path, keys)
    consumed = load_manifests(
        pra_root,
        "petclinic-2026-05-26",
        public_key=pk,
        verify_signatures=True,
    )
    assert len(consumed.column_mappings) == 16

    llm_synthesizer.set_llm_backend(_make_petclinic_backend(fail_column="email"))

    out_root = tmp_path / "prb-d3"
    spec_count = 0
    halt_count = 0
    halt_payloads: List[dict] = []
    spec_payloads: List[dict] = []
    for mapping in consumed.column_mappings:
        legacy_col = consumed.column_specs.get(
            f"{mapping.legacy_table}.{mapping.legacy_column}"
        )
        target_col = consumed.target_column_specs.get(
            f"{mapping.target_table}.{mapping.target_column}"
        )
        blockers = findings_for(consumed.findings, mapping)
        property_set = property_generator.generate_properties(
            mapping, blockers, legacy_column=legacy_col, target_column=target_col
        )
        result = cegis.run_with_cegis(
            mapping=mapping,
            legacy_column=legacy_col,
            target_column=target_col,
            property_set=property_set,
            blockers=blockers,
            max_iterations=3,
        )
        from omnix.dm._types import ReflexionHalt, ReflexionSuccess

        if isinstance(result, ReflexionSuccess):
            path = spec_emitter.emit(
                result,
                migration_id=consumed.migration_id,
                predecessor_hash=consumed.predecessor_hash,
                secret_key=sk,
                public_key=pk,
                output_root=out_root,
            )
            spec_payloads.append(json.loads(path.read_text()))
            spec_count += 1
        elif isinstance(result, ReflexionHalt):
            path = halt_report.emit_halt(
                result,
                migration_id=consumed.migration_id,
                predecessor_hash=consumed.predecessor_hash,
                secret_key=sk,
                public_key=pk,
                output_root=out_root,
            )
            halt_payloads.append(json.loads(path.read_text()))
            halt_count += 1

    if spec_count < 15:
        failed = [p["column_mapping_key"] for p in halt_payloads]
        critiques = [(p["column_mapping_key"], p["last_critique"]) for p in halt_payloads]
        raise AssertionError(
            f"Only {spec_count} specs converged; halts={failed}; "
            f"critiques={critiques}"
        )
    assert halt_count >= 1
    # Chain integrity: every spec + halt's predecessor_hash matches D2's
    # canonical SHA-256.
    for p in spec_payloads + halt_payloads:
        assert p["predecessor_hash"] == consumed.predecessor_hash
    # All specs have non-empty properties_passed; properties_failed empty.
    for p in spec_payloads:
        assert p["properties_passed"]
        assert p["properties_failed"] == []
    # The engineered failure landed on owners.email.
    failed_keys = [p["column_mapping_key"] for p in halt_payloads]
    assert "owners.email" in failed_keys
