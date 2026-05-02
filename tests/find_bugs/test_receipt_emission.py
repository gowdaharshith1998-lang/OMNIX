"""Per-finding receipts + ML-DSA manifest emission and tampering detection."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from axiom import keystore as mldsa_keystore
from axiom.finding_keys import ensure_project_key, project_pubkey_path
from axiom.finding_receipt import now_iso8601_utc
from axiom.merkle import compute_merkle_root, compute_leaf_hash
from find_bugs.receipt_emitter import (
    MissingEd25519ProjectKeyError,
    MissingMldsaKeystoreError,
    emit_scan_receipts,
    verify_scan_directory,
)


def _setup_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[Path, Path]:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    keys = home / ".omnix" / "keys"
    keys.mkdir(parents=True)
    mldsa_keystore.write_keypair_dir(keys)
    return home, keys


def _minimal_finding(file_rel: str = "pkg/a.py") -> dict:
    return {
        "file": file_rel,
        "function": "foo",
        "lineno": 2,
        "severity_score": 22,
        "failures": [
            {
                "exception_type": "AssertionError",
                "message": "boom",
            }
        ],
    }


def test_emit_no_findings_writes_manifest_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pkg").mkdir()
    (proj / "pkg" / "a.py").write_text("# x\n", encoding="utf-8")
    _setup_home(tmp_path, monkeypatch)
    ensure_project_key(proj.resolve())
    scan_dir = emit_scan_receipts(
        [],
        proj.resolve(),
        scan_started_at=now_iso8601_utc(),
        scan_finished_at=now_iso8601_utc(),
        files_scanned=3,
    )
    names = sorted(p.name for p in scan_dir.iterdir())
    assert names == ["scan_manifest.json", "scan_manifest.sig"]
    man = json.loads((scan_dir / "scan_manifest.json").read_text(encoding="utf-8"))
    assert man["finding_count"] == 0
    assert man["merkle_root"] == compute_merkle_root([])


def test_emit_one_finding_writes_four_artifacts(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pkg").mkdir()
    (proj / "pkg" / "a.py").write_text(
        "def foo():\n    assert False\n", encoding="utf-8"
    )
    _setup_home(tmp_path, monkeypatch)
    ensure_project_key(proj.resolve())
    scan_dir = emit_scan_receipts(
        [_minimal_finding()],
        proj.resolve(),
        scan_started_at=now_iso8601_utc(),
        scan_finished_at=now_iso8601_utc(),
        files_scanned=1,
    )
    assert len(list(scan_dir.glob("*.json"))) == 2
    assert len(list(scan_dir.glob("*.sig"))) == 2
    man = json.loads((scan_dir / "scan_manifest.json").read_text(encoding="utf-8"))
    fid = man["finding_leaves"][0]["finding_id"]
    assert (scan_dir / f"{fid}.json").is_file()
    assert (scan_dir / f"{fid}.sig").is_file()


def test_emit_n_findings_file_count(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pkg").mkdir()
    (proj / "pkg" / "a.py").write_text("def a():\n  pass\n", encoding="utf-8")
    (proj / "pkg" / "b.py").write_text("def b():\n  pass\n", encoding="utf-8")
    _setup_home(tmp_path, monkeypatch)
    ensure_project_key(proj.resolve())
    f1 = _minimal_finding("pkg/a.py")
    f2 = dict(_minimal_finding("pkg/b.py"))
    f2["function"] = "b"
    f2["lineno"] = 1
    scan_dir = emit_scan_receipts(
        [f1, f2],
        proj.resolve(),
        scan_started_at=now_iso8601_utc(),
        scan_finished_at=now_iso8601_utc(),
        files_scanned=2,
    )
    all_files = list(scan_dir.iterdir())
    assert len(all_files) == 6


def test_manifest_merkle_root_matches_recomputed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pkg").mkdir()
    (proj / "pkg" / "a.py").write_text("def foo():\n  pass\n", encoding="utf-8")
    _setup_home(tmp_path, monkeypatch)
    ensure_project_key(proj.resolve())
    scan_dir = emit_scan_receipts(
        [_minimal_finding()],
        proj.resolve(),
        scan_started_at=now_iso8601_utc(),
        scan_finished_at=now_iso8601_utc(),
        files_scanned=1,
    )
    man = json.loads((scan_dir / "scan_manifest.json").read_text(encoding="utf-8"))
    leaves: list[bytes] = []
    for ent in man["finding_leaves"]:
        fp = scan_dir / f'{ent["finding_id"]}.json'
        leaves.append(compute_leaf_hash(fp.read_bytes()))
    assert compute_merkle_root(leaves) == man["merkle_root"]


def test_manifest_finding_leaves_sorted_ascending(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pkg").mkdir()
    (proj / "pkg" / "a.py").write_text("def x():\n pass\n", encoding="utf-8")
    (proj / "pkg" / "b.py").write_text("def y():\n pass\n", encoding="utf-8")
    _setup_home(tmp_path, monkeypatch)
    ensure_project_key(proj.resolve())
    f2 = dict(_minimal_finding("pkg/b.py"))
    f2["function"] = "y"
    scan_dir = emit_scan_receipts(
        [_minimal_finding(), f2],
        proj.resolve(),
        scan_started_at=now_iso8601_utc(),
        scan_finished_at=now_iso8601_utc(),
        files_scanned=2,
    )
    man = json.loads((scan_dir / "scan_manifest.json").read_text(encoding="utf-8"))
    ids = [x["finding_id"] for x in man["finding_leaves"]]
    assert ids == sorted(ids)


def test_emit_without_ed25519_key_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    keys = home / ".omnix" / "keys"
    keys.mkdir(parents=True)
    mldsa_keystore.write_keypair_dir(keys)
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "a.py").write_text("def f():\n pass\n", encoding="utf-8")
    with pytest.raises(MissingEd25519ProjectKeyError):
        emit_scan_receipts(
            [_minimal_finding("a.py")],
            proj.resolve(),
            scan_started_at=now_iso8601_utc(),
            files_scanned=1,
        )


def test_emit_without_mldsa_keystore_raises(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    (home / ".omnix" / "keys").mkdir(parents=True)
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pkg").mkdir()
    (proj / "pkg" / "a.py").write_text("def foo():\n pass\n", encoding="utf-8")
    ensure_project_key(proj.resolve())
    with pytest.raises(MissingMldsaKeystoreError):
        emit_scan_receipts(
            [_minimal_finding()],
            proj.resolve(),
            scan_started_at=now_iso8601_utc(),
            files_scanned=1,
        )


def test_verify_scan_directory_clean_returns_ok(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pkg").mkdir()
    (proj / "pkg" / "a.py").write_text("def foo():\n pass\n", encoding="utf-8")
    _home, keys = _setup_home(tmp_path, monkeypatch)
    ensure_project_key(proj.resolve())
    scan_dir = emit_scan_receipts(
        [_minimal_finding()],
        proj.resolve(),
        scan_started_at=now_iso8601_utc(),
        scan_finished_at=now_iso8601_utc(),
        files_scanned=1,
    )
    ok, reason = verify_scan_directory(
        scan_dir,
        project_pubkey_path(proj.resolve()),
        keys / "public.pem",
    )
    assert ok and reason == "ok"


def test_tamper_finding_json_breaks_merkle(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pkg").mkdir()
    (proj / "pkg" / "a.py").write_text("def foo():\n pass\n", encoding="utf-8")
    _home, keys = _setup_home(tmp_path, monkeypatch)
    ensure_project_key(proj.resolve())
    scan_dir = emit_scan_receipts(
        [_minimal_finding()],
        proj.resolve(),
        scan_started_at=now_iso8601_utc(),
        files_scanned=1,
    )
    fj = next(p for p in scan_dir.glob("*.json") if p.name != "scan_manifest.json")
    raw = fj.read_bytes()
    fj.write_bytes(raw[:-3] + b"XXX" + raw[-2:])
    ok, reason = verify_scan_directory(
        scan_dir,
        project_pubkey_path(proj.resolve()),
        keys / "public.pem",
    )
    assert not ok
    assert reason in ("merkle_mismatch", "finding_signature_invalid")


def test_delete_finding_json_breaks_verify(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pkg").mkdir()
    (proj / "pkg" / "a.py").write_text("def foo():\n pass\n", encoding="utf-8")
    _home, keys = _setup_home(tmp_path, monkeypatch)
    ensure_project_key(proj.resolve())
    scan_dir = emit_scan_receipts(
        [_minimal_finding()],
        proj.resolve(),
        scan_started_at=now_iso8601_utc(),
        files_scanned=1,
    )
    fj = next(p for p in scan_dir.glob("*.json") if p.name != "scan_manifest.json")
    (
        scan_dir / f"{fj.stem}.sig"
    ).unlink()
    fj.unlink()
    ok, reason = verify_scan_directory(
        scan_dir,
        project_pubkey_path(proj.resolve()),
        keys / "public.pem",
    )
    assert not ok and reason == "missing_finding"


def test_tamper_manifest_breaks_mldsa_signature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    proj = tmp_path / "proj"
    proj.mkdir()
    (proj / "pkg").mkdir()
    (proj / "pkg" / "a.py").write_text("def foo():\n pass\n", encoding="utf-8")
    _home, keys = _setup_home(tmp_path, monkeypatch)
    ensure_project_key(proj.resolve())
    scan_dir = emit_scan_receipts(
        [_minimal_finding()],
        proj.resolve(),
        scan_started_at=now_iso8601_utc(),
        files_scanned=1,
    )
    mp = scan_dir / "scan_manifest.json"
    orig = mp.read_bytes()
    mp.write_bytes(orig.replace(b'"finding_count"', b'"finding_count_X"', 1))
    ok, reason = verify_scan_directory(
        scan_dir,
        project_pubkey_path(proj.resolve()),
        keys / "public.pem",
    )
    assert not ok and reason == "invalid_manifest_signature"


def test_default_find_bugs_run_writes_no_receipt_scan_dirs(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Regression: without ``emit_receipts``, no ``receipts/findings`` tree."""
    import sqlite3

    from find_bugs import runner

    home = tmp_path / "h"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    proj = tmp_path / "code"
    proj.mkdir()
    (proj / "x.py").write_text("def f():\n pass\n", encoding="utf-8")
    gdb = tmp_path / "db.sqlite"
    c = sqlite3.connect(gdb)
    c.executescript(
        """
CREATE TABLE IF NOT EXISTS nodes (
    id TEXT PRIMARY KEY, name TEXT NOT NULL, type TEXT NOT NULL,
    file_path TEXT, start_line INTEGER, end_line INTEGER,
    complexity INTEGER DEFAULT 0, metadata TEXT
);
CREATE TABLE IF NOT EXISTS edges (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id TEXT NOT NULL, target_id TEXT NOT NULL,
    relationship TEXT NOT NULL, metadata TEXT
);
"""
    )
    c.close()
    ex, _out, _d = runner.run_find_bugs(
        str(proj),
        examples=1,
        top=3,
        json_mode=True,
        no_bundle=True,
        turboscan=False,
        graph_db=str(gdb),
        emit_receipts=False,
    )
    assert ex in (0, 1, 2)
    findings_root = home / ".omnix" / "receipts" / "findings"
    assert not findings_root.exists()
