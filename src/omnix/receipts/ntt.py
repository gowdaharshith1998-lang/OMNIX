# Compliance: P12 — reduction uses %; NTT in pure Python is a known side-channel / timing leak (accepted).
# Compliance: P11, P16

"""FIPS 204, Algorithms 41 (NTT) and 42 (NTT^{-1}); Appendix B (zetas)."""

from __future__ import annotations

from . import params as P


def _bitrev8(m: int) -> int:
    """FIPS 204, Algorithm 43 (8-bit)."""
    b = f"{(m & 0xFF):08b}"
    b_rev = b[::-1]
    return int(b_rev, 2)


# ζ^BitRev8(i) mod Q for i=0..255 (FIPS 204, §2.5, §7.5, Appendix B — generate to avoid table typos)
ZETAS: list[int] = [
    pow(P.ZETA, _bitrev8(i), P.Q) for i in range(256)
]


def ntt(f: list[int]) -> list[int]:
    """
    FIPS 204, Algorithm 41: NTT (same loop structure as ML-DSA reference, §7.5).
    """
    w: list[int] = list(f)
    m = 0
    length = 128
    while length > 0:
        start = 0
        while start < 256:
            m += 1
            z = ZETAS[m] % P.Q
            for j in range(start, start + length):
                t = (z * w[j + length]) % P.Q
                w[j + length] = (w[j] - t) % P.Q
                w[j] = (w[j] + t) % P.Q
            start = length + (j + 1)
        length //= 2
    return w


def ntt_inv(f_hat: list[int]) -> list[int]:
    """
    FIPS 204, Algorithm 42: inverse NTT.
    """
    w: list[int] = list(f_hat)
    m = 256
    length = 1
    while length < 256:
        start = 0
        while start < 256:
            m -= 1
            z = (-ZETAS[m]) % P.Q
            for j in range(start, start + length):
                t0 = w[j]
                w[j] = (t0 + w[j + length]) % P.Q
                w[j + length] = (t0 - w[j + length]) % P.Q
                w[j + length] = (z * w[j + length]) % P.Q
            start = j + length + 1
        length <<= 1
    for j in range(256):
        w[j] = (P.F * w[j]) % P.Q
    return w


def add_ntt(a: list[int], b: list[int]) -> list[int]:
    return [((a[i] + b[i]) % P.Q) for i in range(256)]


def sub_ntt(a: list[int], b: list[int]) -> list[int]:
    return [((a[i] - b[i]) % P.Q) for i in range(256)]


def mult_ntt(a: list[int], b: list[int]) -> list[int]:
    return [((a[i] * b[i]) % P.Q) for i in range(256)]


def matrix_vector_mul_ntt(
    a_hat: list[list[list[int]]], v_hat: list[list[int]]
) -> list[list[int]]:
    """A (k x l) ∘ v (l) in T_q, result k polys in T_q."""
    k, l = P.K, P.L
    out: list[list[int]] = [[0] * 256 for _ in range(k)]
    for r in range(k):
        for s in range(l):
            pr = mult_ntt(a_hat[r][s], v_hat[s])
            out[r] = add_ntt(out[r], pr)
    return out
