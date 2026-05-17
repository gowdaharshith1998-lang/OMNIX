# Compliance: P11, P13, P14
"""
FIPS 204 §7.3: SampleInBall, RejNTTPoly, RejBoundedPoly, ExpandA, ExpandS, ExpandMask.
"""

from __future__ import annotations

from . import encoding, hashing, ntt, params as P


def rej_ntt_poly(seed34: bytes) -> list[int]:
    """
    FIPS 204, Algorithm 30: output in T_q (NTT domain), 256 coefficients mod Q.
    """
    if len(seed34) != 34:  # pragma: no cover
        raise ValueError("RejNTTPoly seed length")
    buf = hashing.g_bytes(seed34, 3000)
    off = 0
    ahat: list[int] = [0] * 256
    j = 0
    while j < 256:
        if off + 3 > len(buf):  # pragma: no cover
            raise RuntimeError("RejNTTPoly buffer")
        s0, s1, s2 = buf[off], buf[off + 1], buf[off + 2]
        off += 3
        c = encoding.coeff_from_three_bytes(s0, s1, s2)
        if c is not None:
            ahat[j] = c % P.Q
            j += 1
    return ahat


def expand_a(rho: bytes) -> list[list[list[int]]]:
    """
    FIPS 204, Algorithm 32: k x l matrix in T_q.
    """
    if len(rho) != P.RHO_SIZE:
        raise ValueError("rho length")
    ahat: list[list[list[int]]] = []
    for r in range(P.K):
        row: list[list[int]] = []
        for s in range(P.L):
            seed = rho + encoding.integer_to_bytes(s, 1) + encoding.integer_to_bytes(r, 1)
            row.append(rej_ntt_poly(seed))
        ahat.append(row)
    return ahat


def rej_bounded_poly(seed66: bytes) -> list[int]:
    """FIPS 204, Algorithm 31."""
    if len(seed66) != 66:
        raise ValueError("RejBoundedPoly seed")
    buf = hashing.h_bytes(seed66, 600)
    off = 0
    a = [0] * 256
    j = 0
    while j < 256:
        if off >= len(buf):  # pragma: no cover
            raise RuntimeError("RejBoundedPoly buffer")
        z = buf[off]
        off += 1
        z0 = encoding.coeff_from_half_byte(z % 16)
        z1 = encoding.coeff_from_half_byte(z // 16)
        if z0 is not None:
            a[j] = z0
            j += 1
        if z1 is not None and j < 256:
            a[j] = z1
            j += 1
    # Coefficients in (-η, η); do not apply c % Q — Python's % would map −1 to Q−1.
    return a


def expand_s(rho_prime: bytes) -> tuple[list[list[int]], list[list[int]]]:
    """FIPS 204, Algorithm 33."""
    if len(rho_prime) != P.RHO_PRIME_SIZE:
        raise ValueError("rho' length")
    s1: list[list[int]] = []
    for r in range(P.L):
        seed = rho_prime + encoding.integer_to_bytes(r, 2)
        s1.append(rej_bounded_poly(seed))
    s2: list[list[int]] = []
    for r in range(P.K):
        seed = rho_prime + encoding.integer_to_bytes(r + P.L, 2)
        s2.append(rej_bounded_poly(seed))
    return s1, s2


def expand_mask(rho_double: bytes, kappa: int) -> list[list[int]]:
    """
    FIPS 204, Algorithm 34: y ∈ R^l; each coefficient in (−γ1+1, γ1).
    """
    if len(rho_double) != 64:
        raise ValueError("expand mask seed")
    c = 1 + encoding.bitlen_u64(P.GAMMA1 - 1)  # 20
    y: list[list[int]] = []
    for r in range(P.L):
        seed = rho_double + encoding.integer_to_bytes(kappa + r, 2)
        buf = hashing.h_bytes(seed, 32 * c)
        y.append(encoding.bit_unpack(buf, P.GAMMA1 - 1, P.GAMMA1))
    return y


def sample_in_ball(rho: bytes) -> list[int]:
    """
    FIPS 204, Algorithm 29: ρ is λ/4 bytes (c_tilde).
    """
    if len(rho) != P.C_TILDE_SIZE:
        raise ValueError("SampleInBall seed length")
    buf = hashing.h_bytes(rho, 400)
    off = 0
    signs = buf[off : off + 8]
    off += 8
    hbits = encoding.bytes_to_bits(signs)
    c = [0] * 256
    for i in range(256 - P.TAU, 256):
        while True:
            if off >= len(buf):
                raise RuntimeError("SampleInBall")  # pragma: no cover
            j = buf[off]
            off += 1
            if j <= i:
                break
        ci = c[j]
        c[i] = ci
        sign = hbits[i + P.TAU - 256]
        c[j] = 1 - 2 * sign  # (-1)^bit: 0 -> 1, 1 -> -1
    return c


