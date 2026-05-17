"""FIPS 204 bit packing: roundtrip inverses."""

from __future__ import annotations

import omnix.axiom.encoding as enc
import omnix.axiom.params as P


def test_bit_pack_vector_roundtrip() -> None:
    a = 4
    b = 4
    w = [i % (a + b + 1) - a for i in range(P.N)]
    packed = enc.bit_pack(w, a, b)
    u = enc.bit_unpack(packed, a, b)
    assert u == w


def test_simple_bit_roundtrip() -> None:
    bnd = 100
    w = [i % (bnd + 1) for i in range(P.N)]
    p = enc.simple_bit_pack(w, bnd)
    u = enc.simple_bit_unpack(p, bnd)
    assert u == w


def test_pk_encode_decode_roundtrip() -> None:
    rho = b"z" * P.RHO_SIZE
    t1 = [[(i * j) % 512 for j in range(P.N)] for i in range(1, P.K + 1)]
    pk = enc.pk_encode(rho, t1)
    assert len(pk) == P.PK_SIZE
    dec = enc.pk_decode(pk)
    assert dec is not None
    r2, t1b = dec
    assert r2 == rho
    assert t1b == t1
