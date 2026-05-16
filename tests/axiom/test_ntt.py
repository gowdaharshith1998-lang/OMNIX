"""FIPS 204 NTT / inverse roundtrip."""

from __future__ import annotations

import secrets

import omnix.axiom.ntt as ntt
import omnix.axiom.params as P


def _randpoly() -> list[int]:
    return [secrets.randbelow(P.Q) for _ in range(P.N)]


def test_ntt_inv_roundtrip() -> None:
    for _ in range(3):
        f = _randpoly()
        t = ntt.ntt(f)
        g = ntt.ntt_inv(t)
        assert f == g


def test_zero_poly_roundtrip() -> None:
    z = [0] * P.N
    assert ntt.ntt_inv(ntt.ntt(z)) == z
