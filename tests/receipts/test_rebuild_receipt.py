"""Schema + signing tests for omnix.receipts.rebuild_receipt.

Honesty-gate coverage: v2 receipts must never emit legacy 'deferred_m2',
and a passed gate must never carry exception details.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from omnix.receipts.rebuild_receipt import (
    GATE_NAMES,
    M2_DEFERRED_GATES,
    SCHEMA_VERSION,
    GateResult,
    HonestyGateError,
    RebuildReceipt,
    default_skipped_gate_results,
    sha256_hex_text,
    sign_rebuild,
    verify_rebuild,
)

_VALID_TS = "2026-05-17T10:00:00.000Z"
_HEX64 = "a" * 64


def _valid_gates(*, gate3_passed: bool = True) -> tuple[GateResult, ...]:
    """Build a full 6-gate tuple with v2 skipped defaults."""
    return (
        GateResult(1, GATE_NAMES[1], "passed"),
        GateResult(2, GATE_NAMES[2], "passed"),
        GateResult(3, GATE_NAMES[3], "passed" if gate3_passed else "failed"),
        GateResult(4, GATE_NAMES[4], "skipped"),
    ) + default_skipped_gate_results()


def _valid_receipt(**overrides) -> RebuildReceipt:
    base = dict(
        project_id="0123456789abcdef",
        node_fqn="org.example.Foo.bar",
        target_language="java21",
        legacy_source_sha256=_HEX64,
        rebuilt_source_sha256="b" * 64,
        spec_hash="c" * 64,
        prompt_template_version="v1-2026-05-17",
        prompt_text_hash="d" * 64,
        model="claude-opus-4.7",
        gate_results=_valid_gates(),
        timestamp=_VALID_TS,
        omnix_version="0.6.1",
    )
    base.update(overrides)
    return RebuildReceipt(**base)


# ----- Schema validation ---------------------------------------------------


def test_valid_receipt_constructs() -> None:
    r = _valid_receipt()
    assert r.schema_version == SCHEMA_VERSION
    assert len(r.gate_results) == 6


def test_invalid_project_id_raises() -> None:
    with pytest.raises(ValueError, match="project_id must be 16 lowercase hex"):
        _valid_receipt(project_id="not-hex")


def test_invalid_hash_field_raises() -> None:
    with pytest.raises(ValueError, match="legacy_source_sha256 must be 64"):
        _valid_receipt(legacy_source_sha256="short")


def test_invalid_timestamp_raises() -> None:
    with pytest.raises(ValueError, match="ISO 8601"):
        _valid_receipt(timestamp="2026-05-17T10:00:00Z")  # missing milliseconds


def test_missing_gates_raises() -> None:
    only_some = (
        GateResult(1, GATE_NAMES[1], "passed"),
        GateResult(2, GATE_NAMES[2], "passed"),
    )
    with pytest.raises(ValueError, match="exactly gates 1..6"):
        _valid_receipt(gate_results=only_some)


def test_duplicate_gates_raises() -> None:
    dupes = (
        GateResult(1, GATE_NAMES[1], "passed"),
        GateResult(1, GATE_NAMES[1], "passed"),  # dup gate 1
        GateResult(3, GATE_NAMES[3], "passed"),
        GateResult(4, GATE_NAMES[4], "skipped"),
    ) + default_skipped_gate_results()
    with pytest.raises(ValueError, match="exactly gates 1..6"):
        _valid_receipt(gate_results=dupes)


# ----- HONESTY GATE — load-bearing -----------------------------------------


@pytest.mark.parametrize("gate_num", sorted(M2_DEFERRED_GATES))
def test_gate_5_and_6_accept_real_v2_statuses(gate_num: int) -> None:
    assert GateResult(gate_num, GATE_NAMES[gate_num], "passed").status == "passed"
    assert GateResult(gate_num, GATE_NAMES[gate_num], "failed").status == "failed"


def test_gate_result_rejects_legacy_deferred_m2_status() -> None:
    with pytest.raises(HonestyGateError, match=r"deferred_m2"):
        GateResult(5, GATE_NAMES[5], "deferred_m2")  # type: ignore[arg-type]


def test_default_skipped_gate_results_are_canonical() -> None:
    gates = default_skipped_gate_results()
    assert {g.gate_number for g in gates} == M2_DEFERRED_GATES
    for g in gates:
        assert g.status == "skipped"
        assert g.details["reason"] == "gate_not_wired"


def test_receipt_level_honesty_invariant_enforced() -> None:
    """Even if a caller bypassed GateResult's __post_init__ (e.g. via
    construction-time crafting), the RebuildReceipt's __post_init__ catches
    it. Defense in depth."""
    bad = GateResult(5, GATE_NAMES[5], "skipped")
    object.__setattr__(bad, "status", "deferred_m2")
    gates = (
        GateResult(1, GATE_NAMES[1], "passed"),
        GateResult(2, GATE_NAMES[2], "passed"),
        GateResult(3, GATE_NAMES[3], "passed"),
        GateResult(4, GATE_NAMES[4], "skipped"),
        bad,
        GateResult(6, GATE_NAMES[6], "skipped"),
    )
    with pytest.raises(HonestyGateError, match="deferred_m2"):
        _valid_receipt(gate_results=gates)


# ----- canonical_json determinism -----------------------------------------


def test_canonical_json_is_deterministic() -> None:
    """Two receipts built from the same inputs sign-equal."""
    r1 = _valid_receipt()
    r2 = _valid_receipt()
    assert r1.canonical_json() == r2.canonical_json()


def test_canonical_json_gate_order_independent() -> None:
    """Building with shuffled gate_results yields the same canonical bytes."""
    gates_fwd = _valid_gates()
    gates_rev = tuple(reversed(gates_fwd))
    r_fwd = _valid_receipt(gate_results=gates_fwd)
    r_rev = _valid_receipt(gate_results=gates_rev)
    assert r_fwd.canonical_json() == r_rev.canonical_json()


def test_from_dict_round_trip() -> None:
    r = _valid_receipt()
    d = r.to_dict()
    r2 = RebuildReceipt.from_dict(d)
    assert r.canonical_json() == r2.canonical_json()


# ----- Sign / verify -------------------------------------------------------


@pytest.fixture
def project_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, str]:
    """Generate a real Ed25519 project key under tmp $HOME so signing works."""
    monkeypatch.setenv("HOME", str(tmp_path))
    # finding_keys uses Path.home() — patched via HOME env above
    from omnix.receipts.finding_keys import (
        ensure_project_key,
        project_pubkey_path,
    )
    from omnix.receipts.finding_receipt import compute_project_id

    project_root = tmp_path / "proj"
    project_root.mkdir()
    ensure_project_key(project_root)
    project_id = compute_project_id(project_root)
    pub_path = project_pubkey_path(project_root)
    return pub_path, project_id


def test_sign_then_verify_round_trip(project_key: tuple[Path, str]) -> None:
    pub_path, project_id = project_key
    r = _valid_receipt(project_id=project_id)
    sig = sign_rebuild(r)
    assert verify_rebuild(r, sig, pub_path) is True


def test_verify_fails_on_tampered_receipt(project_key: tuple[Path, str]) -> None:
    """R-6.4 — tamper detection. Changing ANY byte must flip verified=false."""
    pub_path, project_id = project_key
    r = _valid_receipt(project_id=project_id)
    sig = sign_rebuild(r)

    # Tamper by changing the rebuilt source hash.
    tampered = _valid_receipt(
        project_id=project_id, rebuilt_source_sha256="0" * 64
    )
    assert verify_rebuild(tampered, sig, pub_path) is False


def test_verify_fails_on_tampered_gate_results(project_key: tuple[Path, str]) -> None:
    """Tampering gate details (e.g. silently marking a failed gate passed)
    must flip verified=false even though gate count + numbers match."""
    pub_path, project_id = project_key
    r = _valid_receipt(project_id=project_id, gate_results=_valid_gates(gate3_passed=False))
    sig = sign_rebuild(r)

    tampered = _valid_receipt(project_id=project_id, gate_results=_valid_gates(gate3_passed=True))
    assert verify_rebuild(tampered, sig, pub_path) is False


def test_verify_returns_false_on_malformed_signature(project_key: tuple[Path, str]) -> None:
    pub_path, project_id = project_key
    r = _valid_receipt(project_id=project_id)
    assert verify_rebuild(r, "not-base64!!!", pub_path) is False


def test_sign_raises_without_project_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    # Generate a project_id that has NO corresponding private key on disk.
    r = _valid_receipt(project_id="ffffffffffffffff")
    with pytest.raises(FileNotFoundError, match="omnix axiom keygen"):
        sign_rebuild(r)


def test_sha256_hex_text_round_trip() -> None:
    assert sha256_hex_text("") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
    assert sha256_hex_text("hello") == (
        "2cf24dba5fb0a30e26e83b2ac5b9e29e1b161e5c1fa7425e73043362938b9824"
    )
