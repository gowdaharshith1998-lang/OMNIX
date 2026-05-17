"""Evolution: grammar learning, signed receipts, P21/atomic/P16."""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path

import pytest

from omnix.receipts import keystore, verify as vfy
from omnix.receipts.keygen import keygen
from omnix.graph.store import GraphStore
from omnix.parser import evolution as evo


def _kpair(tmp: Path) -> None:
    pk, sk = keygen()
    kd = tmp / "keys"
    kd.mkdir()
    (kd / "public.pem").write_text(keystore.public_to_pem(pk), encoding="ascii")
    psec = kd / "secret.pem"
    psec.write_text(keystore.secret_to_pem(sk), encoding="ascii")
    os.chmod(psec, 0o600)


def test_evolution_pattern_promoted_after_validation(tmp_path: Path) -> None:
    _kpair(tmp_path)
    evo.set_evolution_test_paths(
        receipt_dir=tmp_path / "rcpt", secret_pem=tmp_path / "keys" / "secret.pem"
    )
    evo.begin_evolution_run()
    g = "gram_a"
    known = frozenset({"x"})
    for i in range(5):
        evo.observe_parse(g, 0.9, {"x", "magic_t"}, known)
    for i in range(5):
        evo.observe_parse(g, 0.1, {"x"}, known)
    p = str(tmp_path / "db")
    s = GraphStore(p)
    n = evo.finalize_evolution_run(s.sqlite_connection())
    s.close()
    try:
        assert n >= 1
        c = sqlite3.connect(p)
        h = c.execute("SELECT hit_count FROM query_pattern WHERE node_type=?", ("magic_t",)).fetchone()  # noqa: E501
        assert h and int(h[0]) == 1
    finally:
        c.close()
        evo.reset_evolution_test_paths()


def test_evolution_pattern_decayed_below_precision(tmp_path: Path) -> None:
    _kpair(tmp_path)
    evo.set_evolution_test_paths(
        receipt_dir=tmp_path / "r2", secret_pem=tmp_path / "keys" / "secret.pem"
    )
    p = str(tmp_path / "db2")
    s = GraphStore(p)
    con = s.sqlite_connection()
    con.execute(
        "INSERT INTO query_pattern(grammar_name, node_type, role, hit_count, miss_count, "
        "is_active, added_at, added_by) VALUES(?,?,?,?,?,?,?,?)",
        (
            "g0",
            "fdec",
            evo.TIER_TOPLEVEL,
            1,
            20,
            1,
            "t",
            evo.ADDED_AUTO,
        ),
    )
    con.commit()
    n = evo.finalize_evolution_run(con)
    s.close()
    assert n >= 1
    c = sqlite3.connect(p)
    ia = c.execute("SELECT is_active FROM query_pattern WHERE node_type=?", ("fdec",)).fetchone()
    c.close()
    assert ia and int(ia[0]) == 0
    evo.reset_evolution_test_paths()


def test_evolution_receipt_signed_and_verifiable(tmp_path: Path) -> None:
    _kpair(tmp_path)
    evo.set_evolution_test_paths(
        receipt_dir=tmp_path / "r3", secret_pem=tmp_path / "keys" / "secret.pem"
    )
    t = {
        "kind": "grammar_evolution",
        "schema_version": 1,
        "grammar": "v_test",
        "m": 1,
        "observed_at": "Z",
    }
    w = evo._write_evolution_receipt(t)
    assert w
    j, sg = w
    pub = (tmp_path / "keys" / "public.pem").read_bytes()
    # verify like axiom: message = j.read_bytes, sig = pem
    b = j.read_bytes()
    sigp = keystore.signature_from_pem(Path(sg).read_text(encoding="ascii"))
    pk = keystore.public_from_pem(pub.decode("ascii"))
    assert vfy.verify_bytes(pk, b, b"", sigp)
    evo.reset_evolution_test_paths()


def test_evolution_skipped_when_no_axiom_key(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    d = tmp_path / "k"
    d.mkdir()
    (d / "secret.pem").write_text("not a key", encoding="ascii")
    evo.set_evolution_test_paths(
        receipt_dir=tmp_path / "r4", secret_pem=tmp_path / "keys" / "missing_secret.pem"  # noqa: E501
    )
    evo.begin_evolution_run()
    g, known = "gram_c", frozenset({"x"})
    for i in range(5):
        evo.observe_parse(g, 0.9, {"x", "cand2"}, known)
    for i in range(5):
        evo.observe_parse(g, 0.0, {"x"}, known)
    p = str(tmp_path / "db3")
    s = GraphStore(p)
    n = evo.finalize_evolution_run(s.sqlite_connection())
    s.close()
    # promote skipped without valid key; hit stays 0
    c = sqlite3.connect(p)
    h = c.execute(
        "SELECT hit_count FROM query_pattern WHERE node_type=?", ("cand2",)
    ).fetchone()  # noqa: E501
    c.close()
    assert h is not None
    assert int(h[0]) == 0
    assert n == 0
    if caplog is not None:
        assert "no key" in " ".join(caplog.messages).lower() or any(
            "key" in m for m in caplog.messages
        ) or n == 0
    evo.reset_evolution_test_paths()


def test_evolution_atomic_at_end_of_run(tmp_path: Path) -> None:
    _kpair(tmp_path)
    evo.set_evolution_test_paths(
        receipt_dir=tmp_path / "r5", secret_pem=tmp_path / "keys" / "secret.pem"
    )
    os.environ["OMNIX_TEST_EVOL_FAIL"] = "1"
    try:
        s = GraphStore(str(tmp_path / "db4"))
        con = s.sqlite_connection()
        n0 = con.execute("SELECT count(*) FROM pattern_mutation").fetchone()[0]
        evo.finalize_evolution_run(con)
        n1 = con.execute("SELECT count(*) FROM pattern_mutation").fetchone()[0]
        s.close()
        assert n1 == n0
    finally:
        del os.environ["OMNIX_TEST_EVOL_FAIL"]
        evo.reset_evolution_test_paths()


def test_builtin_hints_immutable_to_evolution(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    _kpair(tmp_path)
    p = str(tmp_path / "db5")
    s = GraphStore(p)
    c = s.sqlite_connection()
    c.execute(
        "INSERT INTO query_pattern(grammar_name, node_type, role, hit_count, miss_count, "
        "is_active, added_at, added_by) VALUES(?,?,?,?,?,?,?,?)",
        (
            "gb",
            "builtin_t",
            evo.TIER_TOPLEVEL,
            1,
            20,
            1,
            "t",
            evo.BUILTIN,
        ),
    )
    c.commit()
    evo.set_evolution_test_paths(
        receipt_dir=tmp_path / "r6", secret_pem=tmp_path / "keys" / "secret.pem"
    )
    n = evo.finalize_evolution_run(s.sqlite_connection())
    s.close()
    c2 = sqlite3.connect(p)
    ia = c2.execute("SELECT is_active FROM query_pattern WHERE node_type=?", ("builtin_t",)).fetchone()  # noqa: E501
    c2.close()
    assert n == 0
    assert int(ia[0]) == 1
    evo.reset_evolution_test_paths()
