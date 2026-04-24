# Compliance: P11, P13, P15, P20

"""
FIPS 204, Algorithm 2 (ML-DSA.Sign) and Algorithm 7 (Sign_internal).
Constant-time: rejection loop and secret polynomial ops follow spec;
timing side-channels in pure-Python NTT/loops are a known risk (FIPS, Appendix C).
"""

from __future__ import annotations

from . import encoding, hashing, ntt, poly, params as P, sampling


def _modpm_q(r: int) -> int:
    """z mod± q: centered representative (FIPS signature encoding)."""
    t = r % P.Q
    if t > P.Q // 2:
        t -= P.Q
    return t


def _z_modpm(z: list[list[int]]) -> list[list[int]]:
    return [[_modpm_q(c) for c in row] for row in z]


def _count_hint_ones(h: list[list[int]]) -> int:
    n = 0
    for i in range(P.K):
        for j in range(P.N):
            if h[i][j] not in (0, 1):
                raise ValueError("hint not binary")
            if h[i][j] == 1:
                n += 1
    return n


def _hash_mu(tr: bytes, mprime_bits: list[int]) -> bytes:
    b = encoding.bytes_to_bits(tr) + mprime_bits
    return hashing.h_bytes(encoding.bits_to_bytes(b), 64)


def sign_internal(
    sk: bytes, mprime_bits: list[int], rnd: bytes, deterministic: bool
) -> bytes:
    """
    FIPS 204, Algorithm 7: Sign_internal(sk, M', rnd).
    """
    if deterministic:
        if rnd != b"\x00" * P.RND_SIZE:
            raise ValueError("deterministic mode requires zero rnd")
    if len(rnd) != P.RND_SIZE:
        raise ValueError("rnd length")
    rho, k_key, tr, s1, s2, t0 = encoding.sk_decode(sk)
    s1h = [ntt.ntt(p) for p in s1]
    s2h = [ntt.ntt(p) for p in s2]
    t0h = [ntt.ntt(p) for p in t0]
    ahat = sampling.expand_a(rho)
    mu = _hash_mu(tr, mprime_bits)
    rho2 = hashing.h_bytes(k_key + rnd + mu, 64)
    kappa = 0
    z: list[list[int]] | None = None
    hin: list[list[int]] | None = None
    c_tilde: bytes | None = None
    while z is None:
        y = sampling.expand_mask(rho2, kappa)
        yh = [ntt.ntt(yi) for yi in y]
        wv = ntt.matrix_vector_mul_ntt(ahat, yh)
        w = [ntt.ntt_inv(wv[i]) for i in range(P.K)]
        w1 = [poly.high_bits_vec(w[i]) for i in range(P.K)]
        c_tilde = hashing.h_bytes(
            mu + encoding.w1_encode(w1), P.C_TILDE_SIZE
        )
        cpol = sampling.sample_in_ball(c_tilde)
        ch = ntt.ntt(cpol)
        cs1 = [ntt.ntt_inv(ntt.mult_ntt(ch, s1h[i])) for i in range(P.L)]
        cs2 = [ntt.ntt_inv(ntt.mult_ntt(ch, s2h[i])) for i in range(P.K)]
        z_try = [poly.add_r(y[i], cs1[i]) for i in range(P.L)]
        r0 = [poly.sub_r(w[i], cs2[i]) for i in range(P.K)]
        r0b = [poly.low_bits_vec(r0[i]) for i in range(P.K)]
        ok = (
            poly.inf_norm_r_vec(z_try) < P.GAMMA1 - P.BETA
            and poly.inf_norm_r_vec(r0b) < P.GAMMA2 - P.BETA
        )
        if not ok:
            kappa += P.L
            continue
        ct0 = [ntt.ntt_inv(ntt.mult_ntt(ch, t0h[i])) for i in range(P.K)]
        w_m = [
            poly.add_r(poly.sub_r(w[i], cs2[i]), ct0[i]) for i in range(P.K)
        ]
        h_try = [
            poly.make_hint(poly.neg_r(ct0[i]), w_m[i]) for i in range(P.K)
        ]
        if poly.inf_norm_r_vec(ct0) >= P.GAMMA2 or _count_hint_ones(
            h_try
        ) > P.OMEGA:
            kappa += P.L
            continue
        z, hin = z_try, h_try
        kappa += P.L
    if c_tilde is None or z is None or hin is None:
        raise RuntimeError("signing failed")
    return encoding.sig_encode(c_tilde, _z_modpm(z), hin)


def sign_bytes(sk: bytes, msg: bytes, ctx: bytes, rnd: bytes | None) -> bytes:
    """
    FIPS 204, Algorithm 2: M' = BytesToBits(prefix)||M (message bits);
    if rnd is None, deterministic (all zero); else hedged.
    """
    mprime = encoding.message_prime_pure(ctx, msg)
    if rnd is None:
        r = b"\x00" * 32
        return sign_internal(sk, mprime, r, True)
    if len(rnd) != 32:
        raise ValueError("rnd")
    return sign_internal(sk, mprime, rnd, False)
