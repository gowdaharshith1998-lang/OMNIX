"""Grammar health API routes (localhost-only, read-only DB)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from src.studio import server as studio_server
from src.studio.server import app


@pytest.fixture
def grammar_project(tmp_path: Path) -> Path:
    """Minimal tree with ``.omnix/omnix.db`` (evolution schema)."""
    root = tmp_path / "proj"
    omnix_dir = root / ".omnix"
    omnix_dir.mkdir(parents=True)
    db_path = omnix_dir / "omnix.db"
    conn = sqlite3.connect(str(db_path))
    from src.parser.evolution_schema import apply_evolution_schema

    apply_evolution_schema(conn)
    conn.execute(
        "INSERT INTO grammar_profile (grammar_name, first_seen_at, total_files_parsed, "
        "total_quality_score) VALUES (?, ?, ?, ?)",
        ("python", "2026-01-01T00:00:00Z", 10, 6.83),
    )
    conn.execute(
        "INSERT INTO query_pattern (grammar_name, node_type, role, hit_count, miss_count, "
        "is_active, added_at, added_by) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        ("python", "call", "callee", 1, 0, 1, "2026-01-01T00:00:00Z", "builtin_hint"),
    )
    conn.execute(
        "INSERT INTO pattern_mutation (grammar_name, mutation_kind, pattern_id, reason, "
        "observed_at, receipt_path, sig_path) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            "python",
            "promote",
            1,
            "node_ctx",
            "2026-05-01T12:00:00Z",
            "/tmp/ev_r.json",
            "/tmp/ev_r.sig",
        ),
    )
    conn.execute(
        "INSERT INTO unknown_extensions (extension, first_seen_at) VALUES (?, ?)",
        (".foo", "2026-01-01T00:00:00Z"),
    )
    conn.commit()
    conn.close()
    return root


def test_status_route_returns_200_with_data(
    grammar_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(studio_server, "INITIAL_STUDIO_PATH", str(grammar_project.resolve()))
    c = TestClient(app)
    r = c.get("/api/grammar/status")
    assert r.status_code == 200
    data = r.json()
    assert "grammars" in data
    assert data["grammars"][0]["grammar_name"] == "python"
    assert "db_path" in data


def test_status_route_grammar_filter(
    grammar_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(studio_server, "INITIAL_STUDIO_PATH", str(grammar_project.resolve()))
    c = TestClient(app)
    r = c.get("/api/grammar/status", params={"grammar": "python"})
    assert r.status_code == 200
    assert len(r.json()["grammars"]) == 1


def test_status_route_localhost_only(
    grammar_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(studio_server, "INITIAL_STUDIO_PATH", str(grammar_project.resolve()))
    c = TestClient(app)
    r = c.get("/api/grammar/status", headers={"Host": "evil.com"})
    assert r.status_code == 403


def test_mutations_route_returns_list(
    grammar_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(studio_server, "INITIAL_STUDIO_PATH", str(grammar_project.resolve()))
    c = TestClient(app)
    r = c.get("/api/grammar/mutations", params={"limit": 10})
    assert r.status_code == 200
    body = r.json()
    assert "mutations" in body
    assert len(body["mutations"]) == 1
    assert body["mutations"][0]["grammar_name"] == "python"


def test_mutations_route_includes_receipt_existence_flags(
    grammar_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(studio_server, "INITIAL_STUDIO_PATH", str(grammar_project.resolve()))
    c = TestClient(app)
    r = c.get("/api/grammar/mutations")
    m0 = r.json()["mutations"][0]
    assert m0["receipt_exists"] is False
    assert m0["sig_exists"] is False


def test_unknown_extensions_route_returns_valid_json(
    grammar_project: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(studio_server, "INITIAL_STUDIO_PATH", str(grammar_project.resolve()))
    c = TestClient(app)
    r = c.get("/api/grammar/unknown-extensions")
    assert r.status_code == 200
    body = json.loads(r.text)
    assert body["total"] >= 1
    assert isinstance(body["extensions"], list)
    assert body["extensions"][0]["ext"].startswith(".")


def test_llm_budget_route_returns_safe_defaults_when_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        studio_server,
        "read_llm_budget_state",
        lambda: {
            "budget_total": None,
            "budget_remaining": None,
            "calls_today": None,
            "available": False,
        },
    )
    c = TestClient(app)
    r = c.get("/api/fabric/llm-budget")
    assert r.status_code == 200
    assert r.json()["available"] is False


def test_verify_receipt_route_happy_path(monkeypatch: pytest.MonkeyPatch) -> None:
    receipts = Path.home() / ".omnix" / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    f = receipts / "_test_verify.json"
    f.write_text("{}", encoding="utf-8")
    (receipts / "_test_verify.sig").write_text("dummy", encoding="ascii")

    def fake_run(*_a: object, **_k: object) -> mock.Mock:
        m = mock.Mock()
        m.returncode = 0
        m.stdout = "Signature verified successfully\n"
        m.stderr = ""
        return m

    monkeypatch.setattr(studio_server.subprocess, "run", fake_run)
    c = TestClient(app)
    r = c.post(
        "/api/grammar/verify-receipt",
        json={"receipt_path": str(f.resolve())},
    )
    assert r.status_code == 200
    assert r.json()["verified"] is True


def test_verify_receipt_route_rejects_path_traversal() -> None:
    c = TestClient(app)
    r = c.post(
        "/api/grammar/verify-receipt",
        json={"receipt_path": "/etc/passwd"},
    )
    assert r.status_code == 400


def test_verify_receipt_route_handles_missing_receipt(monkeypatch: pytest.MonkeyPatch) -> None:
    receipts = Path.home() / ".omnix" / "receipts"
    receipts.mkdir(parents=True, exist_ok=True)
    ghost = receipts / "_no_such_receipt_omnix_test.json"
    if ghost.exists():
        ghost.unlink()
    c = TestClient(app)
    r = c.post(
        "/api/grammar/verify-receipt",
        json={"receipt_path": str(ghost.resolve())},
    )
    assert r.status_code == 404
