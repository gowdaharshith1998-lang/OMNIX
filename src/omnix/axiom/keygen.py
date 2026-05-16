# Compliance: P15, P20

"""
FIPS 204, Algorithm 1 (KeyGen) and Algorithm 6 (KeyGen_internal).
"""

from __future__ import annotations

from . import encoding, hashing, ntt, poly, params as P, sampling


def keygen_internal(xi: bytes) -> tuple[bytes, bytes]:
    """
    FIPS 204, Algorithm 6: internal key pair from 32-byte seed ξ.
    (ρ, ρ', K) ← H(ξ || IntToBytes(k,1) || IntToBytes(l,1), 128).
    """
    if len(xi) != P.SEED_E_SIZE:
        raise ValueError("KeyGen seed length")
    h_in = (
        xi
        + encoding.integer_to_bytes(P.K, 1)
        + encoding.integer_to_bytes(P.L, 1)
    )
    ext = hashing.h_bytes(h_in, 128)
    rho, rho_p, k_key = ext[:32], ext[32:96], ext[96:128]
    ahat = sampling.expand_a(rho)
    s1, s2 = sampling.expand_s(rho_p)
    s1h = [ntt.ntt(p) for p in s1]
    wv = ntt.matrix_vector_mul_ntt(ahat, s1h)
    t: list[list[int]] = [
        poly.add_r(ntt.ntt_inv(wv[i]), s2[i]) for i in range(P.K)
    ]
    t1: list[list[int]] = []
    t0: list[list[int]] = []
    for i in range(P.K):
        a1, a0 = poly.power2round_vec(t[i])
        t1.append(a1)
        t0.append(a0)
    pk = encoding.pk_encode(rho, t1)
    tr = hashing.h_bytes(pk, 64)
    if len(tr) != P.TR_SIZE:
        raise RuntimeError("tr size")  # pragma: no cover
    sk = encoding.sk_encode(rho, k_key, tr, s1, s2, t0)
    return pk, sk


def keygen() -> tuple[bytes, bytes]:
    """FIPS 204, Algorithm 1: sample ξ, call KeyGen_internal."""
    import secrets

    xi = secrets.token_bytes(32)
    return keygen_internal(xi)
