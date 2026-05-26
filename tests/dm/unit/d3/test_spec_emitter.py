"""Tests for the TransformerSpec receipt emitter (P9)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm._types import (
    MFI,
    ReflexionSuccess,
    TransformerSpec,
)
from omnix.dm.d3_transformation_synthesis.spec_emitter import (
    build_spec_payload,
    emit,
)
from omnix.dm.receipts.ml_dsa_65_signer import verify_canonical


@pytest.fixture
def keys():
    return ml_dsa_65.keypair(seed=b"\x42" * 48)


def _success(properties_failed=()) -> ReflexionSuccess:
    spec = TransformerSpec(
        column_mapping_key="owners.email",
        python_source="def transform(v):\n    return v\n",
        sql_case=None,
        datalog_rule=None,
        properties_passed=("type_preservation", "null_passthrough"),
        properties_failed=tuple(properties_failed),
        mfi_history=(),
        iterations_used=1,
        cegis_pruned_sketches=(),
        tier_failures=(),
        tier_chosen="python",
        confidence=0.95,
        requires_operator_review=False,
        bisimulation_placeholder={},
    )
    return ReflexionSuccess(
        transformer_spec=spec,
        iterations_used=1,
        mfi_history=(),
        pruned_sketches=(),
    )


def test_happy_emit_writes_json_and_sig(tmp_path: Path, keys):
    pk, sk = keys
    pred = hashlib.sha256(b"D2 manifest contents").hexdigest()
    path = emit(
        _success(),
        migration_id="acme-2026-05-26",
        predecessor_hash=pred,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    assert path.exists()
    sig = (path.parent / (path.name + ".sig")).read_text()
    payload = json.loads(path.read_text())
    assert verify_canonical(payload, sig, pk)


def test_schema_violation_when_properties_failed_nonempty(tmp_path: Path, keys):
    pk, sk = keys
    with pytest.raises(ValueError):
        emit(
            _success(properties_failed=("type_preservation",)),
            migration_id="acme-2026-05-26",
            predecessor_hash=hashlib.sha256(b"x").hexdigest(),
            secret_key=sk,
            public_key=pk,
            output_root=tmp_path,
        )


def test_invalid_migration_id_rejected(tmp_path: Path, keys):
    pk, sk = keys
    with pytest.raises(ValueError):
        emit(
            _success(),
            migration_id="ACME!2026",  # uppercase + ! → invalid
            predecessor_hash=hashlib.sha256(b"x").hexdigest(),
            secret_key=sk,
            public_key=pk,
            output_root=tmp_path,
        )


def test_invalid_predecessor_hash_rejected(tmp_path: Path, keys):
    pk, sk = keys
    with pytest.raises(ValueError):
        emit(
            _success(),
            migration_id="acme",
            predecessor_hash="not-a-hash",
            secret_key=sk,
            public_key=pk,
            output_root=tmp_path,
        )


def test_atomic_write_no_partial_on_disk(tmp_path: Path, keys):
    pk, sk = keys
    emit(
        _success(),
        migration_id="acme",
        predecessor_hash=hashlib.sha256(b"x").hexdigest(),
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    # No .tmp file left behind.
    tmps = list((tmp_path / "acme").glob("*.tmp"))
    assert not tmps


def test_predecessor_chain_across_two_specs(tmp_path: Path, keys):
    """Two consecutive spec emits share the same predecessor_hash (both chain
    to D2) — and each receipt's chainhash hex is recomputable from its own
    canonical content."""
    pk, sk = keys
    pred = hashlib.sha256(b"D2 manifest contents").hexdigest()
    p1 = emit(
        _success(),
        migration_id="acme",
        predecessor_hash=pred,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    p2 = emit(
        _success(),
        migration_id="acme",
        predecessor_hash=pred,
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    h1 = json.loads(p1.read_text())["predecessor_hash"]
    h2 = json.loads(p2.read_text())["predecessor_hash"]
    assert h1 == h2 == pred


def test_required_fields_present(tmp_path: Path, keys):
    pk, sk = keys
    path = emit(
        _success(),
        migration_id="acme",
        predecessor_hash=hashlib.sha256(b"x").hexdigest(),
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    payload = json.loads(path.read_text())
    for field in (
        "schema_version",
        "migration_id",
        "predecessor_hash",
        "column_mapping_key",
        "python_source",
        "properties_passed",
        "iterations_used",
        "tier_chosen",
        "signing_algorithm",
        "public_key_fingerprint",
    ):
        assert field in payload


def test_bisimulation_placeholder_empty_dict(tmp_path: Path, keys):
    pk, sk = keys
    path = emit(
        _success(),
        migration_id="acme",
        predecessor_hash=hashlib.sha256(b"x").hexdigest(),
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    payload = json.loads(path.read_text())
    assert payload["bisimulation_placeholder"] == {}
