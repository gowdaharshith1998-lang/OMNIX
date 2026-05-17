"""FIPS 204: sign and verify roundtrip (hedged and deterministic)."""

from __future__ import annotations

import omnix.axiom.keygen as kg
import omnix.axiom.params as P
import omnix.axiom.sign as sgn
import omnix.axiom.verify as vfy


def test_sign_verify_roundtrip_deterministic() -> None:
    pk, sk = kg.keygen_internal(b"k" * 32)
    msg = b"hello, quantum world"
    ctx = b""
    sig = sgn.sign_bytes(sk, msg, ctx, None)
    assert len(sig) == P.SIG_SIZE
    assert vfy.verify_bytes(pk, msg, ctx, sig)


def test_sign_verify_context() -> None:
    pk, sk = kg.keygen_internal(b"m" * 32)
    msg = b"msg"
    ctx = b"ctx-9bytes"
    sig = sgn.sign_bytes(sk, msg, ctx, b"\x00" * 32)  # explicit zero rnd: deterministic
    assert vfy.verify_bytes(pk, msg, ctx, sig)
    assert not vfy.verify_bytes(pk, msg, b"", sig)


def test_tamper_fails() -> None:
    pk, sk = kg.keygen_internal(b"n" * 32)
    sig = sgn.sign_bytes(sk, b"x", b"", None)
    assert not vfy.verify_bytes(pk, b"y", b"", sig)
