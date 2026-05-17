"""export-vault zip builder (slice 18d step 3)."""

from __future__ import annotations

import json
import zipfile
from pathlib import Path

import pytest

from omnix.find_bugs.receipt_emitter import emit_scan_receipts
from omnix.receipts.export_vault import build_vault_zip
from omnix.receipts.finding_keys import ensure_project_key, project_pubkey_path


def _minimal_finding(file_rel: str = "pkg/a.py") -> dict:
    return {
        "file": file_rel,
        "function": "foo",
        "lineno": 2,
        "severity_score": 22,
        "failures": [{"exception_type": "AssertionError", "message": "boom"}],
    }


def _prep_project_and_keys(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
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
    (proj / "pkg" / "a.py").write_text("def foo():\n pass\n", encoding="utf-8")
    ensure_project_key(proj.resolve())
    return proj.resolve()


def test_export_vault_clean_scans_zips_correctly(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = _prep_project_and_keys(tmp_path, monkeypatch)
    emit_scan_receipts(
        [_minimal_finding()],
        proj,
        scan_started_at="2026-05-01T12:00:00.000Z",
        scan_finished_at="2026-05-01T12:00:01.000Z",
        files_scanned=1,
    )
    out = tmp_path / "vault.zip"
    dest, n_inc, n_exc = build_vault_zip(proj, out)
    assert dest == out.resolve()
    assert n_inc == 1 and n_exc == 0
    assert out.is_file()


def test_export_vault_excludes_tampered_by_default(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = _prep_project_and_keys(tmp_path, monkeypatch)
    s1 = emit_scan_receipts(
        [_minimal_finding()],
        proj,
        scan_started_at="2026-05-02T12:00:00.000Z",
        scan_finished_at="2026-05-02T12:00:01.000Z",
        files_scanned=1,
    )
    emit_scan_receipts(
        [_minimal_finding()],
        proj,
        scan_started_at="2026-05-03T12:00:00.000Z",
        scan_finished_at="2026-05-03T12:00:01.000Z",
        files_scanned=1,
    )
    fj = next(p for p in s1.glob("*.json") if p.name != "scan_manifest.json")
    fj.unlink()

    out = tmp_path / "vault.zip"
    dest, n_inc, n_exc = build_vault_zip(proj, out)
    assert n_exc >= 1
    assert n_inc == 1

    with zipfile.ZipFile(dest, "r") as zf:
        names = zf.namelist()
        scan_dirs = {n.split("/")[1] for n in names if n.startswith("scans/") and n.count("/") >= 2}
    assert len(scan_dirs) == 1


def test_export_vault_since_filter_works(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = _prep_project_and_keys(tmp_path, monkeypatch)
    emit_scan_receipts(
        [_minimal_finding()],
        proj,
        scan_started_at="2026-04-01T12:00:00.000Z",
        scan_finished_at="2026-04-01T12:00:01.000Z",
        files_scanned=1,
    )
    emit_scan_receipts(
        [_minimal_finding()],
        proj,
        scan_started_at="2026-06-01T12:00:00.000Z",
        scan_finished_at="2026-06-01T12:00:01.000Z",
        files_scanned=1,
    )
    out = tmp_path / "vault.zip"
    _, n_inc, _ = build_vault_zip(proj, out, since_iso="2026-05-01T00:00:00Z")
    assert n_inc == 1


def test_export_vault_no_scans_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = _prep_project_and_keys(tmp_path, monkeypatch)
    out = tmp_path / "vault.zip"
    with pytest.raises(FileNotFoundError, match="no scans found"):
        build_vault_zip(proj, out)


def test_vault_zip_contents_layout(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = _prep_project_and_keys(tmp_path, monkeypatch)
    emit_scan_receipts(
        [_minimal_finding()],
        proj,
        scan_started_at="2026-05-01T12:00:00.000Z",
        scan_finished_at="2026-05-01T12:00:01.000Z",
        files_scanned=1,
    )
    out = tmp_path / "vault.zip"
    dest, _, _ = build_vault_zip(proj, out)

    with zipfile.ZipFile(dest, "r") as zf:
        names = set(zf.namelist())
        assert "README.md" in names
        assert "vault_index.json" in names
        assert "public_keys/ed25519_pubkey.pem" in names
        assert "public_keys/mldsa_pubkey.pem" in names
        assert any(n.startswith("scans/") for n in names)
        idx = json.loads(zf.read("vault_index.json").decode("utf-8"))
        assert idx["scan_count"] >= 1
        assert "project_id" in idx

    ed_pem = project_pubkey_path(proj).read_text(encoding="ascii")
    with zipfile.ZipFile(dest, "r") as zf:
        assert zf.read("public_keys/ed25519_pubkey.pem").decode("ascii") == ed_pem
