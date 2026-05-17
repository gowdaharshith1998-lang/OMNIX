"""Finding receipt schema, project keys, and Ed25519 sign/verify."""

from __future__ import annotations

import base64
from dataclasses import replace
from pathlib import Path

import pytest

from omnix.axiom.finding_keys import (
    InvalidFindingPublicKeyError,
    ensure_project_key,
    project_pubkey_path,
    sign_finding,
    verify_finding,
)
from omnix.axiom.finding_receipt import (
    FindingReceipt,
    compute_finding_id,
    compute_project_id,
    now_iso8601_utc,
)


def _sample_payload(project_id: str, finding_id: str) -> dict:
    return {
        "schema_version": "1.0",
        "finding_id": finding_id,
        "project_id": project_id,
        "file": "pkg/mod.py",
        "line_start": 10,
        "line_end": 12,
        "severity": "med",
        "rule": "rule.test",
        "model": "static",
        "prompt_hash": None,
        "response_hash": None,
        "finding_summary": "roundtrip smoke",
        "code_snippet_hash": "a" * 64,
        "timestamp": "2026-05-04T12:34:56.789Z",
        "omnix_version": "0.1.0",
    }


def test_compute_project_id_deterministic(tmp_path: Path) -> None:
    root = tmp_path.resolve()
    a = compute_project_id(root)
    b = compute_project_id(root)
    assert a == b
    assert len(a) == 16
    assert all(c in "0123456789abcdef" for c in a)


def test_compute_project_id_differs_for_different_paths(
    tmp_path: Path,
) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    assert compute_project_id(a.resolve()) != compute_project_id(b.resolve())


def test_compute_finding_id_deterministic() -> None:
    pid = "a" * 16
    x = compute_finding_id(pid, "f.py", 3, "r.x")
    y = compute_finding_id(pid, "f.py", 3, "r.x")
    assert x == y
    assert len(x) == 32


def test_finding_receipt_canonical_json_sorted() -> None:
    pid = "b" * 16
    fid = "c" * 32
    fr = FindingReceipt.from_dict(_sample_payload(pid, fid))
    a = fr.canonical_json()
    b = fr.canonical_json()
    assert a == b


def test_finding_receipt_invalid_severity_raises() -> None:
    pid = "d" * 16
    fid = "e" * 32
    d = _sample_payload(pid, fid)
    d["severity"] = "urgent"
    with pytest.raises(ValueError, match="severity"):
        FindingReceipt.from_dict(d)


def test_finding_receipt_summary_too_long_raises() -> None:
    pid = "f" * 16
    fid = "a" * 32
    d = _sample_payload(pid, fid)
    d["finding_summary"] = "x" * 201
    with pytest.raises(ValueError, match="finding_summary"):
        FindingReceipt.from_dict(d)


def test_ensure_project_key_creates_when_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    proj = tmp_path / "proj"
    proj.mkdir()
    proj = proj.resolve()
    priv, pub, created = ensure_project_key(proj)
    assert created is True
    assert priv.name == f"{compute_project_id(proj)}.pem"
    assert priv.is_file()
    assert (priv.stat().st_mode & 0o777) == 0o600
    assert pub == project_pubkey_path(proj)
    assert pub.is_file()


def test_ensure_project_key_idempotent_when_present(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    proj = (tmp_path / "p").resolve()
    proj.mkdir()
    a1, b1, c1 = ensure_project_key(proj)
    a2, b2, c2 = ensure_project_key(proj)
    assert c1 is True
    assert c2 is False
    assert a1 == a2 and b1 == b2
    assert a1.read_bytes() == a2.read_bytes()


def test_ensure_project_key_regenerates_pubkey_if_missing(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    proj = (tmp_path / "q").resolve()
    proj.mkdir()
    priv, pub, _ = ensure_project_key(proj)
    pub.unlink()
    assert not pub.exists()
    _, pub2, created = ensure_project_key(proj)
    assert created is False
    assert pub2.is_file()
    assert pub2.read_bytes() == _ed25519_pub_pem_from_priv(priv)


def _ed25519_pub_pem_from_priv(priv_path: Path) -> bytes:
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    pem = priv_path.read_bytes()
    sk = serialization.load_pem_private_key(pem, password=None)
    assert isinstance(sk, Ed25519PrivateKey)
    return sk.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def test_sign_then_verify_roundtrip_returns_true(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    proj = (tmp_path / "r").resolve()
    proj.mkdir()
    ensure_project_key(proj)
    pid = compute_project_id(proj)
    fid = compute_finding_id(pid, "t.py", 10, "rule.test")
    payload = _sample_payload(pid, fid)
    payload["timestamp"] = now_iso8601_utc()
    sig = sign_finding(payload, pid)
    base64.b64decode(sig, validate=True)
    assert verify_finding(payload, sig, project_pubkey_path(proj)) is True


def test_verify_returns_false_on_payload_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    proj = (tmp_path / "s").resolve()
    proj.mkdir()
    ensure_project_key(proj)
    pid = compute_project_id(proj)
    fid = compute_finding_id(pid, "t.py", 10, "rule.test")
    payload = _sample_payload(pid, fid)
    sig = sign_finding(payload, pid)
    bad = dict(payload)
    bad["severity"] = "critical"
    assert verify_finding(bad, sig, project_pubkey_path(proj)) is False


def test_verify_returns_false_on_signature_mutation(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    proj = (tmp_path / "t").resolve()
    proj.mkdir()
    ensure_project_key(proj)
    pid = compute_project_id(proj)
    fid = compute_finding_id(pid, "t.py", 1, "r")
    payload = _sample_payload(pid, fid)
    sig = sign_finding(payload, pid)
    flip = ("B" if sig[0] != "B" else "C") + sig[1:]
    assert verify_finding(payload, flip, project_pubkey_path(proj)) is False


def test_verify_raises_filenotfound_on_missing_pubkey(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    proj = (tmp_path / "u").resolve()
    proj.mkdir()
    ensure_project_key(proj)
    pid = compute_project_id(proj)
    fid = compute_finding_id(pid, "t.py", 1, "r")
    payload = _sample_payload(pid, fid)
    sig = sign_finding(payload, pid)
    pub = project_pubkey_path(proj)
    pub.unlink()
    with pytest.raises(FileNotFoundError, match=str(pub)):
        verify_finding(payload, sig, pub)


def test_verify_raises_on_corrupt_pubkey(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    proj = (tmp_path / "v").resolve()
    proj.mkdir()
    ensure_project_key(proj)
    pid = compute_project_id(proj)
    fid = compute_finding_id(pid, "t.py", 1, "r")
    payload = _sample_payload(pid, fid)
    sig = sign_finding(payload, pid)
    pub = project_pubkey_path(proj)
    pub.write_text("not valid pem", encoding="ascii")
    with pytest.raises(InvalidFindingPublicKeyError):
        verify_finding(payload, sig, pub)


def test_finding_receipt_replace_tamper_verify_false(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("HOME", str(tmp_path))
    proj = (tmp_path / "w").resolve()
    proj.mkdir()
    ensure_project_key(proj)
    pid = compute_project_id(proj)
    fid = compute_finding_id(pid, "a.py", 1, "r1")
    fr = FindingReceipt.from_dict(_sample_payload(pid, fid))
    sig = sign_finding(
        {
            "schema_version": fr.schema_version,
            "finding_id": fr.finding_id,
            "project_id": fr.project_id,
            "file": fr.file,
            "line_start": fr.line_start,
            "line_end": fr.line_end,
            "severity": fr.severity,
            "rule": fr.rule,
            "model": fr.model,
            "prompt_hash": fr.prompt_hash,
            "response_hash": fr.response_hash,
            "finding_summary": fr.finding_summary,
            "code_snippet_hash": fr.code_snippet_hash,
            "timestamp": fr.timestamp,
            "omnix_version": fr.omnix_version,
        },
        pid,
    )
    tampered = replace(fr, severity="critical")
    assert (
        verify_finding(
            {
                "schema_version": tampered.schema_version,
                "finding_id": tampered.finding_id,
                "project_id": tampered.project_id,
                "file": tampered.file,
                "line_start": tampered.line_start,
                "line_end": tampered.line_end,
                "severity": tampered.severity,
                "rule": tampered.rule,
                "model": tampered.model,
                "prompt_hash": tampered.prompt_hash,
                "response_hash": tampered.response_hash,
                "finding_summary": tampered.finding_summary,
                "code_snippet_hash": tampered.code_snippet_hash,
                "timestamp": tampered.timestamp,
                "omnix_version": tampered.omnix_version,
            },
            sig,
            project_pubkey_path(proj),
        )
        is False
    )
