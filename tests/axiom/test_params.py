"""FIPS 204 Table 1 — ML-DSA-65 constants."""

from __future__ import annotations

import axiom.params as P


def test_mldsa_65_table1() -> None:
    assert P.Q == 8_380_417
    assert P.N == 256
    assert P.D == 13
    assert P.TAU == 49
    assert P.GAMMA1 == 2**19 == 524_288
    assert P.GAMMA2 == (P.Q - 1) // 32
    assert P.K == 6
    assert P.L == 5
    assert P.ETA == 4
    assert P.BETA == P.TAU * P.ETA == 196
    assert P.OMEGA == 55
    assert P.PK_SIZE == 1952
    assert P.SK_SIZE == 4032
    assert P.SIG_SIZE == 3309
    assert P.F * P.N % P.Q == 1  # 256^{-1} · 256


def test_ntt_f_inverse() -> None:
    assert pow(P.N, P.Q - 2, P.Q) == P.F  # F ≡ N^{-1} (as used in spec table)
