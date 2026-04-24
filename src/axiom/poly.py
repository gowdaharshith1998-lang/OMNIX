# Compliance: P12, P20

"""FIPS 204 R_q arithmetic, Power2Round, Decompose, hints (§7.4)."""

from __future__ import annotations

from . import params as P


def modq(r: int) -> int:
    return r % P.Q


def modpm(r: int, alpha: int) -> int:
    """
    m mod± α: unique m' in (-ceil(α/2), floor(α/2)] (FIPS 204 §2.3).
    For even α (2^d, 2*γ2), use t > α//2 so α//2 is not mapped to -α/2
    (matches reduce_mod_pm in the ML-DSA reference; Dilithium §7.2).
    """
    t = r % alpha
    if t > alpha // 2:
        t -= alpha
    return t


def inf_norm_r(r: list[int]) -> int:
    """||w||_∞ for w ∈ R_q: max |w_i mod± q| (FIPS 204 §2.3)."""
    out = 0
    for x in r:
        c = modpm(x, P.Q)
        out = max(out, abs(c))
    return out


def inf_norm_r_vec(v: list[list[int]]) -> int:
    m = 0
    for a in v:
        m = max(m, inf_norm_r(a))
    return m


def add_r(a: list[int], b: list[int]) -> list[int]:
    return [modq(a[i] + b[i]) for i in range(P.N)]


def sub_r(a: list[int], b: list[int]) -> list[int]:
    return [modq(a[i] - b[i]) for i in range(P.N)]


def neg_r(a: list[int]) -> list[int]:
    return [modq(-a[i]) for i in range(P.N)]


def mul_scalar_r(f: int, a: list[int]) -> list[int]:
    f = f % P.Q
    return [modq(f * a[i]) for i in range(P.N)]


def add_vec_r(ra: list[list[int]], rb: list[list[int]]) -> list[list[int]]:
    return [add_r(ra[i], rb[i]) for i in range(len(ra))]


def sub_vec_r(ra: list[list[int]], rb: list[list[int]]) -> list[list[int]]:
    return [sub_r(ra[i], rb[i]) for i in range(len(ra))]


def neg_vec_r(ra: list[list[int]]) -> list[list[int]]:
    return [neg_r(ra[i]) for i in range(len(ra))]


def power2round(r: int) -> tuple[int, int]:
    """
    FIPS 204, Algorithm 35: Power2Round.
    r+ ← r mod q, r0 ← r+ mod± 2^d, return ((r+ - r0) / 2^d, r0).
    """
    rp = r % P.Q
    m = 1 << P.D
    r0 = modpm(rp, m)
    r1 = (rp - r0) // m
    return (r1, r0)


def decompose_r(r: int) -> tuple[int, int]:
    """
    FIPS 204, Algorithm 36: Decompose with α = 2*γ2.
    """
    alpha = 2 * P.GAMMA2
    rp = r % P.Q
    r0 = modpm(rp, alpha)
    if (rp - r0) == (P.Q - 1):
        r1 = 0
        r0 = r0 - 1
    else:
        r1 = (rp - r0) // alpha
    return (r1, r0)


def high_bits(r: int) -> int:
    """FIPS 204, Algorithm 37."""
    return decompose_r(r)[0]


def low_bits(r: int) -> int:
    """FIPS 204, Algorithm 38."""
    return decompose_r(r)[1]


def make_hint_int(z: int, r: int) -> int:
    """FIPS 204, Algorithm 39: returns 0/1 in Z."""
    r1 = high_bits(r)
    v1 = high_bits((r + z) % P.Q)  # r+z in Z_q
    return 1 if r1 != v1 else 0


def use_hint_int(h: int, r: int) -> int:
    """
    FIPS 204, Algorithm 40. h ∈ {0,1}, r ∈ Z_q, output in [0, m-1], m = (q-1)/(2γ2).
    """
    m = (P.Q - 1) // (2 * P.GAMMA2)
    r1, r0 = decompose_r(r)
    if h == 1 and r0 > 0:
        return (r1 + 1) % m
    if h == 1 and r0 <= 0:
        return (r1 - 1) % m
    return r1


def power2round_vec(t: list[int]) -> tuple[list[int], list[int]]:
    t1: list[int] = []
    t0: list[int] = []
    for c in t:
        a, b = power2round(c)
        t1.append(a)
        t0.append(b)
    return t1, t0


def decompose_vec(t: list[int]) -> tuple[list[int], list[int]]:
    t1, t0 = [], []
    for c in t:
        a, b = decompose_r(c)
        t1.append(a)
        t0.append(b)
    return t1, t0


def high_bits_vec(t: list[int]) -> list[int]:
    return [high_bits(c) for c in t]


def low_bits_vec(t: list[int]) -> list[int]:
    return [low_bits(c) for c in t]


def make_hint(z: list[int], r: list[int]) -> list[int]:
    return [make_hint_int(z[i], r[i]) for i in range(P.N)]


def use_hint(h: list[int], r: list[int]) -> list[int]:
    return [use_hint_int(h[i], r[i]) for i in range(P.N)]