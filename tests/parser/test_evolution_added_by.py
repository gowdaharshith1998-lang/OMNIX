"""Evolution receipt v2: ``added_by`` and P21 refuse path."""

from __future__ import annotations

import json
import os
import sqlite3
from pathlib import Path

import pytest

from axiom import keystore, verify as vfy
from axiom.keygen import keygen
from src.graph.store import GraphStore
from src.parser import evolution as evo


def _kpair(tmp: Path) -> None:
    pk, sk = keygen()
    kd = tmp / "keys"
    kd.mkdir()
    (kd / "public.pem").write_text(keystore.public_to_pem(pk), encoding="ascii")
    psec = kd / "secret.pem"
    psec.write_text(keystore.secret_to_pem(sk), encoding="ascii")
    os.chmod(psec, 0o600)


def test_v2_receipt_includes_added_by_for_auto_learned(tmp_path: Path) -> None:
    _kpair(tmp_path)
    evo.set_evolution_test_paths(
        receipt_dir=tmp_path / "rcpt", secret_pem=tmp_path / "keys" / "secret.pem"
    )
    evo.begin_evolution_run()
    g, known = "gram_v2", frozenset({"x"})
    for i in range(5):
        evo.observe_parse(g, 0.9, {"x", "magic_t2"}, known)
    for i in range(5):
        evo.observe_parse(g, 0.1, {"x"}, known)
    p = str(tmp_path / "db")
    s = GraphStore(p)
    n = evo.finalize_evolution_run(s.sqlite_connection())
    s.close()
    assert n >= 1
    rdir = tmp_path / "rcpt"
    js = list(rdir.glob("evolution_*.json"))
    assert js, "receipt file expected"
    d = json.loads(js[0].read_text(encoding="utf-8"))
    assert d.get("schema_version") == 2
    assert d.get("added_by") == evo.ADDED_AUTO
    evo.reset_evolution_test_paths()


def test_v1_legacy_receipt_reads_as_unknown_added_by() -> None:
    v1: dict = {"kind": "grammar_evolution", "schema_version": 1, "grammar": "g"}
    assert evo.resolved_added_by_from_receipt(v1) == evo.ADDED_UNKNOWN
    v1a = (Path.home() / ".omnix" / "receipts").expanduser()
    cands = sorted(
        (v1a.glob("evolution_*python*.json")) if v1a.is_dir() else [],
        key=lambda x: x.stat().st_mtime,
        reverse=True,
    )
    if cands:
        try:
            ext = json.loads(cands[0].read_text(encoding="utf-8", errors="replace"))
        except (OSError, json.JSONDecodeError):
            ext = {}
        if isinstance(ext, dict) and int(ext.get("schema_version") or 0) < 2:
            assert evo.resolved_added_by_from_receipt(ext) == evo.ADDED_UNKNOWN
            jpath = cands[0]
            spath = jpath.parent / f"{jpath.stem}.sig"
            pubp = Path.home() / ".omnix" / "keys" / "public.pem"
            if spath.is_file() and pubp.is_file():
                b = jpath.read_bytes()
                sig = keystore.signature_from_pem(
                    spath.read_text(encoding="ascii")
                )
                pk = keystore.public_from_pem(
                    pubp.read_text(encoding="ascii")
                )
                assert vfy.verify_bytes(pk, b, b"", sig)


def test_emit_refuses_builtin_decay_mutation() -> None:
    with pytest.raises(ValueError, match="refused|immutable|P21"):
        evo.emit_evolution_receipt(
            {
                "kind": "grammar_evolution",
                "grammar": "g",
                "mutation": "decay_pattern",
                "node_type": "n",
                "evidence": {},
                "observed_at": "Z",
                "added_by": evo.BUILTIN,
            }
        )
