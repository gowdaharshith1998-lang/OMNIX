"""Tests for the D1 mapping emitter (P4)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm._types import (
    ColumnMapping,
    ColumnSpec,
    SchemaSpec,
    TableSpec,
)
from omnix.dm.d1_schema_understanding import mapping_emitter
from omnix.dm.receipts import merkle_chain
from omnix.dm.receipts.ml_dsa_65_signer import verify_canonical


def _empty_schema(dialect="postgres") -> SchemaSpec:
    return SchemaSpec(
        dialect=dialect,
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


def _mapping(status="ok", confidence=0.92):
    return ColumnMapping(
        legacy_table="owner",
        legacy_column="email",
        target_table="owner",
        target_column="email",
        confidence=confidence,
        status=status,
        candidates=(("owner", "email", confidence),),
        rationale="test",
    )


def test_emit_happy_path(tmp_path: Path):
    pk, sk = ml_dsa_65.keypair()
    out = mapping_emitter.emit(
        mappings=(_mapping(),),
        legacy=_empty_schema(),
        target=_empty_schema(),
        migration_id="acme-2026-05-26",
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    assert out.exists()
    assert out.name == "column-mapping.json"
    sig_path = out.with_suffix(".json.sig")
    assert sig_path.exists()
    body = json.loads(out.read_text())
    sig_hex = sig_path.read_text().strip()
    assert verify_canonical(body, sig_hex, pk) is True
    assert body["schema_version"] == "omnix-dm/column-mapping/v1"
    assert body["stats"]["status_ok_count"] == 1
    assert body["requires_operator_review"] is False


def test_emit_predecessor_chain(tmp_path: Path):
    pk, sk = ml_dsa_65.keypair()
    out1 = mapping_emitter.emit(
        mappings=(_mapping(),),
        legacy=_empty_schema(),
        target=_empty_schema(),
        migration_id="acme",
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    chain_path = out1.parent / "column-mapping.chainhash"
    h1 = chain_path.read_text().strip()
    # Re-emit with predecessor hash from h1 — chain should change
    out2 = mapping_emitter.emit(
        mappings=(_mapping(status="low_confidence", confidence=0.7),),
        legacy=_empty_schema(),
        target=_empty_schema(),
        migration_id="acme-v2",
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
        predecessor_hash=h1,
    )
    body2 = json.loads(out2.read_text())
    assert body2["predecessor_hash"] == h1
    h2 = (out2.parent / "column-mapping.chainhash").read_text().strip()
    assert h1 != h2


def test_emit_schema_violation_does_not_write(tmp_path: Path):
    pk, sk = ml_dsa_65.keypair()
    bad_mapping = ColumnMapping(
        legacy_table="owner",
        legacy_column="email",
        target_table="owner",
        target_column="email",
        confidence=0.92,
        status="completely-invalid-status",  # type: ignore[arg-type]
        candidates=(),
        rationale="",
    )
    with pytest.raises(Exception):
        mapping_emitter.emit(
            mappings=(bad_mapping,),
            legacy=_empty_schema(),
            target=_empty_schema(),
            migration_id="bad",
            secret_key=sk,
            public_key=pk,
            output_root=tmp_path,
        )
    # No file written
    assert not (tmp_path / "bad" / "column-mapping.json").exists()


def test_emit_invalid_migration_id_rejected(tmp_path: Path):
    pk, sk = ml_dsa_65.keypair()
    for bad_id in ("../escape", "WITH-CAPS", "spaces here", "", "x/y"):
        with pytest.raises(ValueError):
            mapping_emitter.emit(
                mappings=(_mapping(),),
                legacy=_empty_schema(),
                target=_empty_schema(),
                migration_id=bad_id,
                secret_key=sk,
                public_key=pk,
                output_root=tmp_path,
            )


def test_emit_requires_review_when_low_confidence(tmp_path: Path):
    pk, sk = ml_dsa_65.keypair()
    out = mapping_emitter.emit(
        mappings=(_mapping(status="low_confidence", confidence=0.7),),
        legacy=_empty_schema(),
        target=_empty_schema(),
        migration_id="lc",
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    body = json.loads(out.read_text())
    assert body["requires_operator_review"] is True
    assert body["stats"]["status_low_confidence_count"] == 1
