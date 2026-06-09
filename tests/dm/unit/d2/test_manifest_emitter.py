"""Tests for the D2 edge-case manifest emitter (P7)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm._types import (
    AnomalyFinding,
    ColumnSpec,
    ProbeRequest,
    ProbeResult,
    SchemaSpec,
    TableSpec,
)
from omnix.dm.d1_schema_understanding.mapping_emitter import _atomic_write
from omnix.dm.d1_schema_understanding.mapping_emitter import emit as emit_d1
from omnix.dm.d2_edge_case_profiling.manifest_emitter import build_manifest, emit
from omnix.dm.receipts.ml_dsa_65_signer import verify_canonical


def _req(cat="null_distribution"):
    return ProbeRequest(
        category=cat,
        legacy_table="owner",
        legacy_column="email",
        priority=0.9,
        estimated_cost_ms=500,
        rationale="t",
    )


def _finding(severity="blocker", **kw):
    return AnomalyFinding(
        probe_category=kw.get("probe_category", "null_distribution"),
        legacy_table=kw.get("legacy_table", "owner"),
        legacy_column=kw.get("legacy_column", "email"),
        anomaly_type=kw.get("anomaly_type", "null_in_non_null_column"),
        severity=severity,
        sample_values=kw.get("sample_values", ()),
        affected_row_count=kw.get("affected_row_count", 5),
        remediation_hint=kw.get("remediation_hint", "fix it"),
        requires_human_decision=kw.get("requires_human_decision", True),
    )


def test_emit_happy_path(tmp_path: Path):
    pk, sk = ml_dsa_65.keypair()
    results = (
        ProbeResult(
            request=_req(),
            findings=(_finding(severity="warn"),),
            status="ok",
            duration_ms=42,
        ),
    )
    out = emit(
        results=results,
        migration_id="acme",
        predecessor_hash="deadbeef" * 8,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    assert out.exists()
    sig_hex = (out.with_suffix(".json.sig")).read_text()
    body = json.loads(out.read_text())
    assert verify_canonical(body, sig_hex, pk) is True
    assert body["stats"]["warn_count"] == 1
    assert body["predecessor_hash"] == "deadbeef" * 8


def test_emit_requires_non_empty_predecessor(tmp_path: Path):
    pk, sk = ml_dsa_65.keypair()
    with pytest.raises(ValueError):
        emit(
            results=(),
            migration_id="x",
            predecessor_hash="",
            secret_key=sk,
            public_key=pk,
            output_root=tmp_path,
        )


def test_emit_with_blocker_requires_review(tmp_path: Path):
    pk, sk = ml_dsa_65.keypair()
    results = (
        ProbeResult(
            request=_req(),
            findings=(_finding(severity="blocker"),),
            status="ok",
            duration_ms=10,
        ),
    )
    out = emit(
        results=results,
        migration_id="m1",
        predecessor_hash="a" * 64,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    body = json.loads(out.read_text())
    assert body["requires_operator_review"] is True
    assert body["stats"]["blocker_count"] == 1


def test_emit_records_probe_failures(tmp_path: Path):
    pk, sk = ml_dsa_65.keypair()
    results = (
        ProbeResult(
            request=_req("orphan_fk"),
            findings=(),
            status="timeout",
            duration_ms=10_001,
            reason="exceeded budget",
        ),
        ProbeResult(
            request=_req("encoding_anomaly"),
            findings=(),
            status="error",
            duration_ms=15,
            reason="ERROR: column does not exist",
        ),
    )
    out = emit(
        results=results,
        migration_id="failmix",
        predecessor_hash="b" * 64,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    body = json.loads(out.read_text())
    assert body["stats"]["timeout_count"] == 1
    assert body["stats"]["error_count"] == 1
    assert len(body["probe_failures"]) == 2


def test_chain_links_to_d1(tmp_path: Path):
    """Emit D1 column-mapping, then D2 with that mapping's chain hash as
    predecessor. Verify the predecessor field matches."""
    from omnix.dm._types import ColumnMapping
    pk, sk = ml_dsa_65.keypair()
    legacy = SchemaSpec(
        dialect="postgres",
        name="default",
        tables=(
            TableSpec(
                name="owner",
                columns=(
                    ColumnSpec(
                        name="email",
                        raw_type="VARCHAR(255)",
                        normalized_type="STRING",
                        nullable=True,
                        default=None,
                        primary_key=False,
                        unique=False,
                        comment=None,
                        dialect_specific={},
                    ),
                ),
                primary_key=(),
            ),
        ),
    )
    mapping = ColumnMapping(
        legacy_table="owner",
        legacy_column="email",
        target_table="owner",
        target_column="email",
        confidence=0.91,
        status="ok",
        candidates=(),
        rationale="",
    )
    d1_path = emit_d1(
        mappings=(mapping,),
        legacy=legacy,
        target=legacy,
        migration_id="chained",
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    chain_hash = (d1_path.parent / "column-mapping.chainhash").read_text().strip()
    d2_path = emit(
        results=(),
        migration_id="chained",
        predecessor_hash=chain_hash,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    body2 = json.loads(d2_path.read_text())
    assert body2["predecessor_hash"] == chain_hash


def test_empty_results_yields_valid_manifest(tmp_path: Path):
    pk, sk = ml_dsa_65.keypair()
    out = emit(
        results=(),
        migration_id="empty",
        predecessor_hash="c" * 64,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    body = json.loads(out.read_text())
    assert body["stats"]["total_probes_run"] == 0
    assert body["stats"]["total_findings"] == 0
