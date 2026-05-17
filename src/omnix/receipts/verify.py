# Compliance: P11, P20

"""FIPS 204, Algorithm 3 (Verify) and Algorithm 8 (Verify_internal)."""

from __future__ import annotations

from . import encoding, hashing, ntt, poly, sampling
from . import params as P


def _hash_mu(tr: bytes, mprime_bits: list[int]) -> bytes:
    b = encoding.bytes_to_bits(tr) + mprime_bits
    return hashing.h_bytes(encoding.bits_to_bytes(b), 64)


def verify_internal(pk: bytes, mprime_bits: list[int], sig: bytes) -> bool:
    """
    FIPS 204, Algorithm 8: Verify_internal(pk, M', σ).
    """
    dec = encoding.pk_decode(pk)
    if dec is None:
        return False
    rho, t1 = dec
    sd = encoding.sig_decode(sig)
    if sd is None:
        return False
    c_tilde, z, h = sd
    # ‖z‖∞ < γ1 − β
    if poly.inf_norm_r_vec(z) >= P.GAMMA1 - P.BETA:
        return False
    if _count_hint_ones(h) > P.OMEGA:
        return False
    ahat = sampling.expand_a(rho)
    tr = hashing.h_bytes(pk, 64)
    mu = _hash_mu(tr, mprime_bits)
    cpol = sampling.sample_in_ball(c_tilde)
    ch = ntt.ntt(cpol)
    zh = [ntt.ntt(zi) for zi in z]
    az = ntt.matrix_vector_mul_ntt(ahat, zh)
    t1_sc = [
        poly.mul_scalar_r(1 << P.D, t1[i]) for i in range(P.K)
    ]
    t1h = [ntt.ntt(tp) for tp in t1_sc]
    wph = [
        ntt.sub_ntt(az[i], ntt.mult_ntt(ch, t1h[i])) for i in range(P.K)
    ]
    wp = [ntt.ntt_inv(wph[i]) for i in range(P.K)]
    w1p = [poly.use_hint(h[i], wp[i]) for i in range(P.K)]
    c2 = hashing.h_bytes(mu + encoding.w1_encode(w1p), P.C_TILDE_SIZE)
    return c2 == c_tilde


def _count_hint_ones(h: list[list[int]]) -> int:
    n = 0
    for i in range(P.K):
        for j in range(P.N):
            if h[i][j] not in (0, 1):
                return 2**30  # force fail
            if h[i][j] == 1:
                n += 1
    return n


def verify_bytes(
    pk: bytes, msg: bytes, ctx: bytes, sig: bytes
) -> bool:
    """FIPS 204, Algorithm 3."""
    mprime = encoding.message_prime_pure(ctx, msg)
    if len(ctx) > 255:
        return False
    return verify_internal(pk, mprime, sig)
