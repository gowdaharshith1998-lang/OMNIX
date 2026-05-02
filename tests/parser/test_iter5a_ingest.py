"""ITER 5a: evolution wiring + ingest dispatch (analyze / find-bugs)."""

from __future__ import annotations

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

import pytest

from src.graph.store import GraphStore
from src.parser import evolution
from src.parser import ingest_dispatch as ind


def test_observe_parse_called_from_analyze_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    n = 0

    def _track(*_a, **_k) -> None:  # noqa: ANN001, ANN002
        nonlocal n
        n += 1

    monkeypatch.setattr("src.parser.evolution.observe_parse", _track)
    (tmp_path / "hi.py").write_text("def f():\n    return 1\n", encoding="utf-8")
    evolution.begin_evolution_run()
    store = GraphStore(str(tmp_path / "db1.sqlite"))
    ind.ingest_unified_codebase(str(tmp_path), store, parse_mode="generic")
    evolution.finalize_evolution_run(store.sqlite_connection())
    store.close()
    assert n >= 1


def test_observe_parse_called_from_find_bugs_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    n = 0

    def _track(*_a, **_k) -> None:  # noqa: ANN001, ANN002
        nonlocal n
        n += 1

    monkeypatch.setattr("src.parser.evolution.observe_parse", _track)
    (tmp_path / "x.py").write_text("def f(): pass\n", encoding="utf-8")
    dbp = tmp_path / "omnix.db"
    s = GraphStore(str(dbp))
    s.close()
    evolution.begin_evolution_run()
    s2 = GraphStore(str(dbp))
    _ = ind.run_evolution_ingest_on_store(s2, tmp_path, 1_000_000, parse_mode="generic")
    evolution.finalize_evolution_run(s2.sqlite_connection())
    s2.close()
    assert n >= 1


def test_finalize_evolution_committed_atomically_at_end_of_run(
    tmp_path: Path,
) -> None:
    evolution.begin_evolution_run()
    evolution.observe_parse("g_lazy", 0.7, {"module"}, frozenset({"module"}))
    p = str(tmp_path / "gl.db")
    s0 = GraphStore(p)
    assert (
        s0.sqlite_connection()
        .execute("SELECT count(*) FROM grammar_profile WHERE grammar_name='g_lazy'")
        .fetchone()[0]
        == 0
    )
    s0.close()
    s1 = GraphStore(p)
    n = evolution.finalize_evolution_run(s1.sqlite_connection())
    s1.close()
    assert n >= 0
    c = sqlite3.connect(p)
    row = c.execute("SELECT total_files_parsed FROM grammar_profile WHERE grammar_name=?", ("g_lazy",)).fetchone()  # noqa: E501
    c.close()
    assert row and int(row[0]) == 1


def test_grammar_list_command_output_shape() -> None:
    root = Path(__file__).resolve().parents[2]
    r = subprocess.run(
        [sys.executable, str(root / "omnix.py"), "grammar", "list"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert r.returncode == 0
    for line in (x for x in r.stdout.splitlines() if x.strip()):
        parts = line.split("\t")
        assert len(parts) == 2
        assert parts[0].startswith("tree_sitter_")


def test_grammar_status_command_returns_per_grammar_summary(
    tmp_path: Path,
) -> None:
    p = str(tmp_path / "odb.sqlite")
    s = GraphStore(p)
    s.sqlite_connection().execute(
        "INSERT INTO grammar_profile(grammar_name, first_seen_at, total_files_parsed, total_quality_score) "  # noqa: E501
        "VALUES(?,?,?,?)",
        ("python", "T", 4, 3.0),
    )
    s.sqlite_connection().commit()
    s.close()
    root = Path(__file__).resolve().parents[2]
    r = subprocess.run(
        [
            sys.executable,
            str(root / "omnix.py"),
            "grammar",
            "status",
            "--db",
            p,
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "python" in r.stdout
    assert "Files parsed" in r.stdout
    assert "0.750" in r.stdout


def test_grammar_verify_command_validates_signature(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    from axiom import keystore, sign
    from axiom.keygen import keygen

    pk, sk = keygen()
    kd = tmp_path / "keys"
    kd.mkdir()
    (kd / "public.pem").write_text(keystore.public_to_pem(pk), encoding="ascii")
    ssec = kd / "secret.pem"
    ssec.write_text(keystore.secret_to_pem(sk), encoding="ascii")
    os.chmod(ssec, 0o600)
    body = b'{"k":1}'
    rj = tmp_path / "r.json"
    rj.write_bytes(body)
    sp = ssec.read_text(encoding="ascii")
    sk2 = keystore.secret_from_pem(sp)
    sigb = sign.sign_bytes(sk2, body, b"", b"\0" * 32)
    (tmp_path / "r.sig").write_text(keystore.signature_to_pem(sigb), encoding="ascii")
    root = Path(__file__).resolve().parents[2]
    r = subprocess.run(
        [
            sys.executable,
            str(root / "omnix.py"),
            "grammar",
            "verify",
            str(rj),
            "--pubkey",
            str(kd / "public.pem"),
        ],
        capture_output=True,
        text=True,
    )
    assert r.returncode == 0
    assert "verified" in (r.stdout + r.stderr).lower()
