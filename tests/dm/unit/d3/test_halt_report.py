"""Tests for the HaltReport emitter (P9)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm._types import MFI, ReflexionHalt, SecurityViolation
from omnix.dm.d3_transformation_synthesis.halt_report import emit_halt
from omnix.dm.receipts.ml_dsa_65_signer import verify_canonical


@pytest.fixture
def keys():
    return ml_dsa_65.keypair(seed=b"\x55" * 48)


def _mfi(name="type_preservation") -> MFI:
    return MFI(
        property_name=name,
        input_value_repr="None",
        expected_output_repr="None",
        actual_output_repr="42",
        hint="should pass null through",
    )


def test_iteration_cap_halt_carries_all_mfis(tmp_path: Path, keys):
    pk, sk = keys
    halt = ReflexionHalt(
        column_mapping_key="owners.email",
        halt_reason="iteration_cap",
        latest_python_source="def transform(v): return 9999",
        failing_mfis=tuple(_mfi(f"prop_{i}") for i in range(5)),
        last_critique="property prop_4 failed",
        iterations_used=5,
    )
    path = emit_halt(
        halt,
        migration_id="acme",
        predecessor_hash=hashlib.sha256(b"d2").hexdigest(),
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    payload = json.loads(path.read_text())
    assert payload["halt_reason"] == "iteration_cap"
    assert len(payload["failing_mfis"]) == 5


def test_security_violation_halt_populates_field(tmp_path: Path, keys):
    pk, sk = keys
    sv = SecurityViolation(
        node_type="Import",
        reason="AST node Import not in allowlist",
        source_excerpt="import os",
    )
    halt = ReflexionHalt(
        column_mapping_key="owners.email",
        halt_reason="security_violation",
        latest_python_source="import os",
        failing_mfis=(),
        last_critique="AST rejected: Import",
        iterations_used=1,
        security_violation=sv,
    )
    path = emit_halt(
        halt,
        migration_id="acme",
        predecessor_hash=hashlib.sha256(b"d2").hexdigest(),
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    payload = json.loads(path.read_text())
    assert payload["security_violation"]["node_type"] == "Import"


def test_parse_failure_halt_records_reason(tmp_path: Path, keys):
    pk, sk = keys
    halt = ReflexionHalt(
        column_mapping_key="x.y",
        halt_reason="parse_failure",
        latest_python_source="",
        failing_mfis=(),
        last_critique="missing python block",
        iterations_used=1,
    )
    path = emit_halt(
        halt,
        migration_id="acme",
        predecessor_hash=hashlib.sha256(b"d2").hexdigest(),
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    payload = json.loads(path.read_text())
    assert payload["halt_reason"] == "parse_failure"
    assert "missing python block" in payload["last_critique"]


def test_atomic_write(tmp_path: Path, keys):
    pk, sk = keys
    halt = ReflexionHalt(
        column_mapping_key="x.y",
        halt_reason="iteration_cap",
        latest_python_source="",
        failing_mfis=(),
        last_critique="",
        iterations_used=5,
    )
    emit_halt(
        halt,
        migration_id="acme",
        predecessor_hash=hashlib.sha256(b"d2").hexdigest(),
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    tmps = list((tmp_path / "acme").glob("*.tmp"))
    assert not tmps


def test_signature_verifies(tmp_path: Path, keys):
    pk, sk = keys
    halt = ReflexionHalt(
        column_mapping_key="x.y",
        halt_reason="iteration_cap",
        latest_python_source="",
        failing_mfis=(),
        last_critique="",
        iterations_used=5,
    )
    path = emit_halt(
        halt,
        migration_id="acme",
        predecessor_hash=hashlib.sha256(b"d2").hexdigest(),
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    sig = (path.parent / (path.name + ".sig")).read_text()
    payload = json.loads(path.read_text())
    assert verify_canonical(payload, sig, pk)


def test_schema_const_holds(tmp_path: Path, keys):
    pk, sk = keys
    halt = ReflexionHalt(
        column_mapping_key="x.y",
        halt_reason="iteration_cap",
        latest_python_source="",
        failing_mfis=(),
        last_critique="",
        iterations_used=5,
    )
    path = emit_halt(
        halt,
        migration_id="acme",
        predecessor_hash=hashlib.sha256(b"d2").hexdigest(),
        secret_key=sk,
        public_key=pk,
        output_root=tmp_path,
    )
    payload = json.loads(path.read_text())
    assert payload["schema_version"] == "omnix-dm/transformer-halt/v1"
    assert payload["signing_algorithm"] == "ML-DSA-65"
