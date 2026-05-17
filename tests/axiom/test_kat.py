"""NIST ACVP FIPS 204 JSON fixtures: ML-DSA-65, first 10 per category."""

from __future__ import annotations

import json
from pathlib import Path

import omnix.axiom.keygen as kg
import omnix.axiom.sign as sgn
import omnix.axiom.verify as vfy
import omnix.axiom.params as P

_KAT = Path(__file__).resolve().parent / "kat_mldsa65.json"


def _load() -> dict:
    with open(_KAT, encoding="utf-8") as f:
        return json.load(f)


def test_keygen_kat() -> None:
    d = _load()
    assert len(d["keygen"]) >= 10
    for t in d["keygen"][:10]:
        seed = bytes.fromhex(t["seed"])
        pk, sk = kg.keygen_internal(seed)
        assert pk == bytes.fromhex(t["pk"])
        assert sk == bytes.fromhex(t["sk"])


def test_sign_kat() -> None:
    d = _load()
    assert len(d["sign"]) >= 10
    for t in d["sign"][:10]:
        sk = bytes.fromhex(t["sk"])
        msg = bytes.fromhex(t["message"])
        ctx = bytes.fromhex(t["context"])
        sig = sgn.sign_bytes(sk, msg, ctx, None)
        assert sig == bytes.fromhex(t["signature"])


def test_verify_kat() -> None:
    d = _load()
    assert len(d["verify"]) >= 10
    for t in d["verify"][:10]:
        pk = bytes.fromhex(t["pk"])
        msg = bytes.fromhex(t["message"])
        ctx = bytes.fromhex(t["context"])
        sig = bytes.fromhex(t["signature"])
        ok = vfy.verify_bytes(pk, msg, ctx, sig)
        assert ok == t["testPassed"]


def test_kat_file_declares_65() -> None:
    d = _load()
    for name in ("keygen", "sign", "verify"):
        for t in d[name][:1]:
            if name == "keygen" and "pk" in t:
                assert len(bytes.fromhex(t["pk"])) == P.PK_SIZE
