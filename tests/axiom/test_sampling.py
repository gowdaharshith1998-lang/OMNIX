"""FIPS 204: SampleInBall, ExpandA dimensions."""

from __future__ import annotations

import omnix.axiom.params as P
import omnix.axiom.sampling as smp


def test_sample_in_ball_tau_nnz() -> None:
    rho = bytes(range(48))  # C_TILDE_SIZE
    c = smp.sample_in_ball(rho)
    assert len(c) == 256
    assert sum(1 for x in c if x != 0) == P.TAU
    for x in c:
        assert x in (-1, 0, 1)


def test_expand_a_shape() -> None:
    rho = b"x" * P.RHO_SIZE
    a = smp.expand_a(rho)
    assert len(a) == P.K
    assert all(len(row) == P.L for row in a)
    assert all(len(p) == 256 for row in a for p in row)


def test_expand_s_shapes() -> None:
    rp = b"y" * P.RHO_PRIME_SIZE
    s1, s2 = smp.expand_s(rp)
    assert len(s1) == P.L and len(s2) == P.K
    for p in s1 + s2:
        assert len(p) == 256
        assert all(-P.ETA <= x <= P.ETA for x in p)
