"""CLI smoke tests for `omnix axiom verify-rebuild`.

`omnix rebuild` itself integrates with the real graph store + dispatch_fn,
so an E2E CLI run is gated by `OMNIX_REAL_LLM=1`. This file covers the
verify side, which is pure offline cryptography + JSON parsing.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from click.testing import CliRunner

from omnix.receipts.cli import axiom_group
from omnix.receipts.finding_keys import ensure_project_key, project_pubkey_path
from omnix.receipts.finding_receipt import compute_project_id
from omnix.receipts.rebuild_receipt import (
    GATE_NAMES,
    GateResult,
    RebuildReceipt,
    default_m2_deferred_gate_results,
    sign_rebuild,
)


def _write_receipt_pair(
    dest_dir: Path, *, project_id: str
) -> tuple[Path, Path]:
    """Build, sign, and persist a valid receipt + sidecar signature."""
    gates = (
        GateResult(1, GATE_NAMES[1], "passed"),
        GateResult(2, GATE_NAMES[2], "passed"),
        GateResult(3, GATE_NAMES[3], "passed"),
        GateResult(4, GATE_NAMES[4], "skipped"),
    ) + default_m2_deferred_gate_results()
    r = RebuildReceipt(
        project_id=project_id,
        node_fqn="org.example.Foo.bar",
        target_language="java21",
        legacy_source_sha256="a" * 64,
        rebuilt_source_sha256="b" * 64,
        spec_hash="c" * 64,
        prompt_template_version="v1-2026-05-17",
        prompt_text_hash="d" * 64,
        model="claude-opus-4.7",
        gate_results=gates,
        timestamp="2026-05-17T10:00:00.000Z",
        omnix_version="0.6.1",
    )
    sig_b64 = sign_rebuild(r)
    dest_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = dest_dir / "Foo.bar.json"
    sig_path = dest_dir / "Foo.bar.sig"
    receipt_path.write_bytes(r.canonical_json())
    sig_path.write_text(sig_b64 + "\n", encoding="utf-8")
    return receipt_path, sig_path


@pytest.fixture
def _signed_receipt(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    project_root = tmp_path / "proj"
    project_root.mkdir()
    ensure_project_key(project_root)
    project_id = compute_project_id(project_root)
    pub_path = project_pubkey_path(project_root)
    out_dir = project_root / ".omnix" / "receipts" / "rebuilds" / "2026-05-17T10-00-00.000Z"
    receipt_path, _sig_path = _write_receipt_pair(out_dir, project_id=project_id)
    return receipt_path, pub_path


def test_verify_rebuild_cli_passes_on_valid_receipt(_signed_receipt) -> None:
    receipt_path, pub_path = _signed_receipt
    runner = CliRunner()
    result = runner.invoke(
        axiom_group,
        [
            "verify-rebuild",
            str(receipt_path),
            "--pubkey",
            str(pub_path),
            "--json",
        ],
    )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["verified"] is True
    assert payload["node_fqn"] == "org.example.Foo.bar"
    assert payload["model"] == "claude-opus-4.7"
    # Honesty gate visible in summary.
    assert "deferred_m2" in payload["gates_summary"]


def test_verify_rebuild_cli_fails_on_tampered_receipt(_signed_receipt) -> None:
    receipt_path, pub_path = _signed_receipt
    # Tamper the on-disk JSON
    raw = json.loads(receipt_path.read_text(encoding="utf-8"))
    raw["rebuilt_source_sha256"] = "0" * 64
    receipt_path.write_text(
        json.dumps(raw, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    runner = CliRunner()
    result = runner.invoke(
        axiom_group,
        [
            "verify-rebuild",
            str(receipt_path),
            "--pubkey",
            str(pub_path),
            "--json",
        ],
    )
    assert result.exit_code == 1, result.output
    payload = json.loads(result.output)
    assert payload["verified"] is False
    assert payload["reason"] == "signature_mismatch"


def test_verify_rebuild_cli_missing_signature_reports_clearly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    project_root = tmp_path / "proj"
    project_root.mkdir()
    ensure_project_key(project_root)
    pub_path = project_pubkey_path(project_root)

    receipt_path = tmp_path / "orphan.json"
    receipt_path.write_text("{}", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        axiom_group,
        [
            "verify-rebuild",
            str(receipt_path),
            "--pubkey",
            str(pub_path),
            "--json",
        ],
    )
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["verified"] is False
    assert payload["reason"] == "missing_sig"


def test_verify_rebuild_cli_malformed_receipt_reports_clearly(
    _signed_receipt: tuple[Path, Path],
) -> None:
    receipt_path, pub_path = _signed_receipt
    receipt_path.write_text("{ not valid json ", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        axiom_group,
        [
            "verify-rebuild",
            str(receipt_path),
            "--pubkey",
            str(pub_path),
            "--json",
        ],
    )
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["verified"] is False
    assert payload["reason"] == "malformed_receipt"
