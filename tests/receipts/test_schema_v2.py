"""Schema v2 coverage for signed rebuild receipts."""

from __future__ import annotations

import base64
import json
from pathlib import Path
from typing import Any

import pytest

from omnix.receipts import rebuild_receipt as rr
from omnix.receipts.finding_keys import (
    _load_private_key,
    ensure_project_key,
    project_privkey_path,
    project_pubkey_path,
)
from omnix.receipts.finding_receipt import compute_project_id

_VALID_TS = "2026-05-17T10:00:00.000Z"
_HEX64 = "a" * 64


def _v2_gates() -> tuple[rr.GateResult, ...]:
    return (
        rr.GateResult(1, rr.GATE_NAMES[1], "passed"),
        rr.GateResult(2, rr.GATE_NAMES[2], "passed"),
        rr.GateResult(3, rr.GATE_NAMES[3], "passed"),
        rr.GateResult(4, rr.GATE_NAMES[4], "skipped"),
        rr.GateResult(
            5,
            rr.GATE_NAMES[5],
            "skipped",
            {"reason": "gate_not_wired"},
        ),
        rr.GateResult(
            6,
            rr.GATE_NAMES[6],
            "skipped",
            {"reason": "gate_not_wired"},
        ),
    )


def _receipt_dict(
    *,
    project_id: str = "0123456789abcdef",
    schema_version: str = "2.0",
    gate_results: tuple[rr.GateResult, ...] | None = None,
) -> dict[str, Any]:
    receipt = rr.RebuildReceipt(
        project_id=project_id,
        node_fqn="org.example.Foo.bar",
        target_language="java21",
        legacy_source_sha256=_HEX64,
        rebuilt_source_sha256="b" * 64,
        spec_hash="c" * 64,
        prompt_template_version="v1-2026-05-17",
        prompt_text_hash="d" * 64,
        model="claude-opus-4.7",
        gate_results=gate_results or _v2_gates(),
        timestamp=_VALID_TS,
        omnix_version="0.6.1",
        schema_version=schema_version,
    )
    return receipt.to_dict()


def _legacy_v1_dict(*, project_id: str = "0123456789abcdef") -> dict[str, Any]:
    d = _receipt_dict(project_id=project_id, schema_version="1.0")
    for gate in d["gate_results"]:
        if gate["gate_number"] in (5, 6):
            gate["status"] = "deferred_m2"
            gate["details"] = {"reason": "M1 deferred"}
    return d


def _canonical_bytes(d: dict[str, Any]) -> bytes:
    payload = dict(d)
    payload["gate_results"] = sorted(
        payload["gate_results"], key=lambda g: int(g["gate_number"])
    )
    return json.dumps(
        payload,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")


def test_schema_v2_is_default_and_contains_exactly_six_gates() -> None:
    receipt = rr.RebuildReceipt.from_dict(_receipt_dict())

    assert rr.SCHEMA_VERSION == "2.0"
    assert receipt.schema_version == "2.0"
    assert [g.gate_number for g in receipt.gate_results] == [1, 2, 3, 4, 5, 6]


def test_schema_v2_rejects_deferred_m2_at_receipt_level() -> None:
    assert hasattr(rr, "HonestyGateError")
    bad = rr.GateResult(5, rr.GATE_NAMES[5], "skipped")
    object.__setattr__(bad, "status", "deferred_m2")
    gates = _v2_gates()[:4] + (bad, _v2_gates()[5])

    with pytest.raises(rr.HonestyGateError, match="deferred_m2"):
        rr.RebuildReceipt.from_dict(_receipt_dict(gate_results=gates))


def test_schema_v2_rejects_passed_gate_with_exception_details() -> None:
    gates = (
        rr.GateResult(1, rr.GATE_NAMES[1], "passed", {"exception": "boom"}),
    ) + _v2_gates()[1:]

    with pytest.raises(rr.HonestyGateError, match="passed.*exception"):
        rr.RebuildReceipt.from_dict(_receipt_dict(gate_results=gates))


def test_from_dict_migrates_v1_deferred_m2_read_only() -> None:
    receipt = rr.RebuildReceipt.from_dict(_legacy_v1_dict())

    assert receipt.schema_version == "1.0"
    by_number = {g.gate_number: g for g in receipt.gate_results}
    assert by_number[5].status == "skipped"
    assert by_number[5].details["migrated_from"] == "deferred_m2"
    assert by_number[6].status == "skipped"
    assert by_number[6].details["migrated_from"] == "deferred_m2"


def test_v2_round_trip_is_byte_identical() -> None:
    receipt = rr.RebuildReceipt.from_dict(_receipt_dict())
    reloaded = rr.RebuildReceipt.from_dict(receipt.to_dict())

    assert receipt.canonical_json() == reloaded.canonical_json()


def test_v1_signature_still_verifies_after_read_migration(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    project_root = tmp_path / "proj"
    project_root.mkdir()
    ensure_project_key(project_root)
    project_id = compute_project_id(project_root)
    pub_path = project_pubkey_path(project_root)

    legacy = _legacy_v1_dict(project_id=project_id)
    original_bytes = _canonical_bytes(legacy)
    priv = _load_private_key(project_privkey_path(project_id))
    sig_b64 = base64.b64encode(priv.sign(original_bytes)).decode("ascii")

    migrated = rr.RebuildReceipt.from_dict(legacy)

    assert rr.verify_rebuild(migrated, sig_b64, pub_path) is True
    assert migrated.to_dict() != legacy


def test_gates_summary_has_all_v2_buckets_and_rolls_crashes_into_failed() -> None:
    gates = (
        rr.GateResult(1, rr.GATE_NAMES[1], "passed"),
        rr.GateResult(2, rr.GATE_NAMES[2], "failed"),
        rr.GateResult(3, rr.GATE_NAMES[3], "runtime_crash"),
        rr.GateResult(4, rr.GATE_NAMES[4], "skipped"),
        rr.GateResult(5, rr.GATE_NAMES[5], "inconclusive"),
        rr.GateResult(6, rr.GATE_NAMES[6], "deferred_m3"),
    )

    assert (
        rr.gates_summary(gates)
        == "1-passed/2-failed/1-skipped/1-inconclusive/1-deferred_m3"
    )
