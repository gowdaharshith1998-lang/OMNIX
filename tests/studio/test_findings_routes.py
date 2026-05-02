"""Finding scans API (localhost-only, read-only vault)."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from src.studio import server as studio_server
from src.studio.server import app


def _minimal_finding(file_rel: str = "pkg/a.py") -> dict:
    return {
        "file": file_rel,
        "function": "foo",
        "lineno": 2,
        "severity_score": 22,
        "failures": [{"exception_type": "AssertionError", "message": "boom"}],
    }


@pytest.fixture
def findings_project(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    from axiom import keystore as mldsa_keystore
    from axiom.finding_keys import ensure_project_key

    keys = home / ".omnix" / "keys"
    keys.mkdir(parents=True)
    mldsa_keystore.write_keypair_dir(keys)

    root = tmp_path / "proj"
    root.mkdir()
    (root / "pkg").mkdir()
    (root / "pkg" / "a.py").write_text("def foo():\n pass\n", encoding="utf-8")
    ensure_project_key(root.resolve())

    from axiom.finding_receipt import now_iso8601_utc
    from find_bugs.receipt_emitter import emit_scan_receipts

    emit_scan_receipts(
        [_minimal_finding()],
        root.resolve(),
        scan_started_at="2026-05-01T10:00:00.000Z",
        scan_finished_at="2026-05-01T10:00:01.000Z",
        files_scanned=1,
    )
    emit_scan_receipts(
        [_minimal_finding()],
        root.resolve(),
        scan_started_at="2026-06-01T12:00:00.000Z",
        scan_finished_at="2026-06-01T12:00:01.000Z",
        files_scanned=1,
    )
    monkeypatch.setattr(studio_server, "INITIAL_STUDIO_PATH", str(root.resolve()))
    return root.resolve()


def test_get_scans_returns_list_sorted_desc(
    findings_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    c = TestClient(app)
    r = c.get("/api/findings/scans")
    assert r.status_code == 200
    scans = r.json()["scans"]
    assert len(scans) >= 2
    ts = [str(s.get("scan_started_at") or "") for s in scans]
    assert ts == sorted(ts, reverse=True)


def test_get_scans_returns_empty_when_no_receipts_dir(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    home = tmp_path / "home"
    home.mkdir()
    monkeypatch.setenv("HOME", str(home))
    from axiom import keystore as mldsa_keystore
    from axiom.finding_keys import ensure_project_key

    keys = home / ".omnix" / "keys"
    keys.mkdir(parents=True)
    mldsa_keystore.write_keypair_dir(keys)

    root = tmp_path / "empty_proj"
    root.mkdir()
    ensure_project_key(root.resolve())
    monkeypatch.setattr(studio_server, "INITIAL_STUDIO_PATH", str(root.resolve()))

    c = TestClient(app)
    r = c.get("/api/findings/scans")
    assert r.status_code == 200
    assert r.json()["scans"] == []


def test_get_scans_localhost_only(findings_project: Path) -> None:
    c = TestClient(app)
    r = c.get("/api/findings/scans", headers={"Host": "evil.com"})
    assert r.status_code == 403


def test_post_verify_scan_clean_returns_verified_true(findings_project: Path) -> None:
    c = TestClient(app)
    listing = c.get("/api/findings/scans").json()["scans"]
    sid = listing[0]["scan_id"]
    r = c.post("/api/findings/verify-scan", json={"scan_id": sid})
    assert r.status_code == 200
    body = r.json()
    assert body["verified"] is True
    assert body["reason"] == "ok"
    assert body["scan_id"] == sid
    assert "manifest_summary" in body
    assert "finding_leaves" not in body.get("manifest_summary", {})


def test_post_verify_scan_tampered_returns_verified_false(
    findings_project: Path,
) -> None:
    c = TestClient(app)
    listing = c.get("/api/findings/scans").json()["scans"]
    sid = listing[0]["scan_id"]
    root = Path(findings_project)
    from axiom.finding_receipt import compute_project_id

    pid = compute_project_id(root)
    receipts = Path.home() / ".omnix" / "receipts" / "findings" / pid / sid
    fj = next(p for p in receipts.glob("*.json") if p.name != "scan_manifest.json")
    fj.unlink()

    r = c.post("/api/findings/verify-scan", json={"scan_id": sid})
    assert r.status_code == 200
    assert r.json()["verified"] is False


def test_post_verify_scan_invalid_scan_id_returns_400(findings_project: Path) -> None:
    c = TestClient(app)
    r = c.post("/api/findings/verify-scan", json={"scan_id": "short"})
    assert r.status_code == 400


def test_post_verify_scan_path_traversal_attempts_return_400(
    findings_project: Path,
) -> None:
    c = TestClient(app)
    for bad in ("../../../etc/passwd", "/etc/passwd", "a/../b"):
        r = c.post("/api/findings/verify-scan", json={"scan_id": bad})
        assert r.status_code == 400, bad


def test_post_verify_scan_not_found(findings_project: Path) -> None:
    c = TestClient(app)
    r = c.post(
        "/api/findings/verify-scan",
        json={"scan_id": "zzzzzzzzzzzzzzzzzzzz"},
    )
    assert r.status_code == 404


def test_post_verify_scan_localhost_only(findings_project: Path) -> None:
    c = TestClient(app)
    listing = c.get("/api/findings/scans").json()["scans"]
    sid = listing[0]["scan_id"]
    r = c.post(
        "/api/findings/verify-scan",
        json={"scan_id": sid},
        headers={"Host": "evil.com"},
    )
    assert r.status_code == 403


def test_get_scans_includes_dir_path_relative(findings_project: Path) -> None:
    c = TestClient(app)
    scans = c.get("/api/findings/scans").json()["scans"]
    for s in scans:
        rel = s.get("dir_path_relative")
        assert isinstance(rel, str)
        assert rel.startswith("findings/")
        assert s["scan_id"] in rel
