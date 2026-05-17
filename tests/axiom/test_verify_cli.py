"""CLI: ``omnix axiom verify-finding`` and ``verify-scan``."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from click.testing import CliRunner

from omnix.receipts.finding_keys import ensure_project_key, project_pubkey_path
from omnix.receipts.finding_receipt import now_iso8601_utc
from omnix.cli import main
from omnix.find_bugs.receipt_emitter import emit_scan_receipts


def _minimal_finding(file_rel: str = "pkg/a.py") -> dict:
    return {
        "file": file_rel,
        "function": "foo",
        "lineno": 2,
        "severity_score": 22,
        "failures": [{"exception_type": "AssertionError", "message": "boom"}],
    }


def _setup_scan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path, Path]:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    from omnix.receipts import keystore as mldsa_keystore

    keys = home / ".omnix" / "keys"
    keys.mkdir(parents=True)
    mldsa_keystore.write_keypair_dir(keys)

    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pkg").mkdir()
    (proj / "pkg" / "a.py").write_text("def foo():\n    assert False\n", encoding="utf-8")
    ensure_project_key(proj.resolve())
    scan_dir = emit_scan_receipts(
        [_minimal_finding()],
        proj.resolve(),
        scan_started_at=now_iso8601_utc(),
        scan_finished_at=now_iso8601_utc(),
        files_scanned=1,
    )
    pub = project_pubkey_path(proj.resolve())
    return proj, scan_dir, pub


def test_verify_finding_clean_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj, scan_dir, pub = _setup_scan(tmp_path, monkeypatch)
    fj = next(p for p in scan_dir.glob("*.json") if p.name != "scan_manifest.json")
    runner = CliRunner()
    r = runner.invoke(
        main,
        ["axiom", "verify-finding", str(fj), "--pubkey", str(pub)],
    )
    assert r.exit_code == 0, r.output
    assert "verified" in r.output.lower()


def test_verify_finding_tampered_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj, scan_dir, pub = _setup_scan(tmp_path, monkeypatch)
    fj = next(p for p in scan_dir.glob("*.json") if p.name != "scan_manifest.json")
    raw = fj.read_bytes()
    fj.write_bytes(raw[:-3] + b"XXX" + raw[-2:])
    runner = CliRunner()
    r = runner.invoke(
        main,
        ["axiom", "verify-finding", str(fj), "--pubkey", str(pub)],
    )
    assert r.exit_code == 1
    assert "FAIL" in r.output or "invalid" in r.output.lower()


def test_verify_finding_missing_sig_returns_2(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj, scan_dir, pub = _setup_scan(tmp_path, monkeypatch)
    fj = next(p for p in scan_dir.glob("*.json") if p.name != "scan_manifest.json")
    fj.with_suffix(".sig").unlink()
    runner = CliRunner()
    r = runner.invoke(
        main,
        ["axiom", "verify-finding", str(fj), "--pubkey", str(pub)],
    )
    assert r.exit_code == 2


def test_verify_finding_json_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj, scan_dir, pub = _setup_scan(tmp_path, monkeypatch)
    fj = next(p for p in scan_dir.glob("*.json") if p.name != "scan_manifest.json")
    runner = CliRunner()
    r = runner.invoke(
        main,
        ["axiom", "verify-finding", str(fj), "--pubkey", str(pub), "--json"],
    )
    assert r.exit_code == 0
    obj = json.loads(r.output.strip())
    assert obj["verified"] is True
    assert obj["reason"] == "ok"
    assert "receipt_path" in obj


def test_verify_scan_clean_returns_0(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj, scan_dir, pub = _setup_scan(tmp_path, monkeypatch)
    mldsa_pub = Path.home() / ".omnix" / "keys" / "public.pem"
    runner = CliRunner()
    r = runner.invoke(
        main,
        [
            "axiom",
            "verify-scan",
            str(scan_dir),
            "--ed25519-pubkey",
            str(pub),
            "--mldsa-pubkey",
            str(mldsa_pub),
        ],
    )
    assert r.exit_code == 0, r.output
    assert "verified" in r.output.lower()


def test_verify_scan_tampered_returns_1(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj, scan_dir, pub = _setup_scan(tmp_path, monkeypatch)
    mldsa_pub = Path.home() / ".omnix" / "keys" / "public.pem"
    fj = next(p for p in scan_dir.glob("*.json") if p.name != "scan_manifest.json")
    fj.unlink()
    runner = CliRunner()
    r = runner.invoke(
        main,
        [
            "axiom",
            "verify-scan",
            str(scan_dir),
            "--ed25519-pubkey",
            str(pub),
            "--mldsa-pubkey",
            str(mldsa_pub),
        ],
    )
    assert r.exit_code == 1


def test_verify_scan_json_format(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj, scan_dir, pub = _setup_scan(tmp_path, monkeypatch)
    mldsa_pub = Path.home() / ".omnix" / "keys" / "public.pem"
    runner = CliRunner()
    r = runner.invoke(
        main,
        [
            "axiom",
            "verify-scan",
            str(scan_dir),
            "--ed25519-pubkey",
            str(pub),
            "--mldsa-pubkey",
            str(mldsa_pub),
            "--json",
        ],
    )
    assert r.exit_code == 0
    obj = json.loads(r.output.strip())
    assert obj["verified"] is True
    assert obj["reason"] == "ok"
    assert "manifest_summary" in obj
    assert "finding_count" in obj


def test_auto_discover_pubkey_walks_up_to_project_root(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """verify-finding discovers ``proj/.omnix/pubkey.pem`` from a nested receipt path."""
    proj, scan_dir, _pub = _setup_scan(tmp_path, monkeypatch)
    fj = next(p for p in scan_dir.glob("*.json") if p.name != "scan_manifest.json")
    nested = proj / "deep" / "nested"
    nested.mkdir(parents=True)
    dest = nested / "copy.json"
    shutil.copy(fj, dest)
    shutil.copy(fj.with_suffix(".sig"), dest.with_suffix(".sig"))
    runner = CliRunner()
    r = runner.invoke(main, ["axiom", "verify-finding", str(dest)])
    assert r.exit_code == 0, r.output
