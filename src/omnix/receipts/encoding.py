# Compliance: P11, P20

"""
FIPS 204 §7.1–7.2: bit/byte conversion, bit packing, key/sig encoding
(Algorithms 9–28).
"""

from __future__ import annotations

from . import params as P


def _bitlen64(x: int) -> int:
    if x < 0:  # pragma: no cover
        raise ValueError("bitlen expected nonnegative")
    # FIPS 204 §2.3: e.g. bitlen(32)=6, bitlen(31)=5 — x.bit_length() for x ≥ 1
    if x == 0:
        return 0
    return x.bit_length()


def bitlen_u64(x: int) -> int:
    """Public bit-length helper (FIPS `bitlen` on small positive integers)."""
    return _bitlen64(x)


def integer_to_bytes(x: int, alpha: int) -> bytes:
    """FIPS 204, Algorithm 11: little-endian base-256, length alpha."""
    o = bytearray()
    y = x
    for _ in range(alpha):
        o.append(y & 0xFF)
        y //= 256
    return bytes(o)


def integer_to_bits(x: int, al: int) -> list[int]:
    """FIPS 204, Algorithm 9: LSB at index 0."""
    y: list[int] = [0] * al
    xp = x
    for i in range(al):
        y[i] = xp & 1
        xp //= 2
    return y


def bits_to_integer(bits: list[int], al: int) -> int:
    """FIPS 204, Algorithm 10: first bit in bits[0] is LSB."""
    x = 0
    for j in range(1, al + 1):
        x = 2 * x + bits[al - j]
    return x


def bytes_to_bits(z: bytes) -> list[int]:
    """FIPS 204, Algorithm 13."""
    y: list[int] = []
    zlist = bytearray(z)
    for i in range(len(z)):
        t = int(zlist[i])
        for j in range(8):
            y.append(t & 1)
            t //= 2
    return y


def bits_to_bytes(bits: list[int]) -> bytes:
    """FIPS 204, Algorithm 12: little-endian in each output byte."""
    al = len(bits)
    n = (al + 7) // 8
    z = bytearray([0] * n)
    for i in range(al):
        z[i // 8] = (z[i // 8] + (bits[i] << (i % 8))) & 0xFF
    return bytes(z)


def coeff_from_three_bytes(b0: int, b1: int, b2: int) -> int | None:
    """FIPS 204, Algorithm 14: ⊥ = None."""
    b2p = b2
    if b2 > 127:
        b2p = b2p - 128
    z = b0 + (b1 << 8) + (b2p << 16)
    if z < P.Q:
        return z
    return None


def coeff_from_half_byte(b: int) -> int | None:
    """FIPS 204, Algorithm 15 for ML-DSA-65 (η = 4)."""
    if P.ETA == 2 and b < 15:
        return 2 - (b % 5)
    if P.ETA == 4 and b < 9:
        return 4 - b
    if P.ETA == 2:
        return None
    return None


def simple_bit_pack(w: list[int], bnd: int) -> bytes:
    """FIPS 204, Algorithm 16."""
    c = _bitlen64(bnd)
    z: list[int] = []
    for i in range(P.N):
        z.extend(integer_to_bits(w[i], c))
    return bits_to_bytes(z)


def simple_bit_unpack(v: bytes, bnd: int) -> list[int]:
    """FIPS 204, Algorithm 18."""
    c = _bitlen64(bnd)
    z = bytes_to_bits(v)
    w: list[int] = []
    for i in range(P.N):
        w.append(bits_to_integer(z[i * c : (i + 1) * c], c))
    return w


def bit_pack(w: list[int], a: int, b: int) -> bytes:
    """FIPS 204, Algorithm 17: encode coefficients in [−a, b] via b − w_i."""
    c = _bitlen64(a + b)
    z: list[int] = []
    for i in range(P.N):
        z.extend(integer_to_bits(b - w[i], c))
    return bits_to_bytes(z)


def bit_unpack(v: bytes, a: int, b: int) -> list[int]:
    """FIPS 204, Algorithm 19."""
    c = _bitlen64(a + b)
    z = bytes_to_bits(v)
    w: list[int] = []
    for i in range(P.N):
        w.append(b - bits_to_integer(z[i * c : (i + 1) * c], c))
    return w


def hint_bit_pack(h: list[list[int]]) -> bytes:
    """
    FIPS 204, Algorithm 20. h ∈ (R2)^k as k binary polys (coeffs 0,1 in Z or Z_q).
    """
    y = bytearray([0] * (P.OMEGA + P.K))
    index = 0
    for i in range(P.K):
        for j in range(P.N):
            if h[i][j] not in (0, 1):  # pragma: no cover
                raise ValueError("hint not binary")
            if h[i][j] != 0:
                y[index] = j
                index += 1
        y[P.OMEGA + i] = index
    return bytes(y)


def hint_bit_unpack(y: bytes) -> list[list[int]] | None:
    """FIPS 204, Algorithm 21."""
    if len(y) != P.OMEGA + P.K:
        return None
    h: list[list[int]] = [[0] * P.N for _ in range(P.K)]
    index = 0
    for i in range(P.K):
        e = y[P.OMEGA + i]
        if e < index or e > P.OMEGA:
            return None
        first = index
        while index < e:
            if index > first and y[index - 1] >= y[index]:
                return None
            h[i][y[index]] = 1
            index += 1
    for j in range(index, P.OMEGA):
        if y[j] != 0:
            return None
    return h


# --- key/signature (Algorithms 22–27) ---


def pk_encode(rho: bytes, t1: list[list[int]]) -> bytes:
    bnd = (1 << P.T1_BITLEN) - 1
    pk = bytearray(rho)
    for i in range(P.K):
        pk.extend(simple_bit_pack(t1[i], bnd))
    return bytes(pk)


def pk_decode(pk: bytes) -> tuple[bytes, list[list[int]]] | None:
    if len(pk) != P.PK_SIZE:
        return None
    bnd = (1 << P.T1_BITLEN) - 1
    rho = pk[: P.RHO_SIZE]
    rest = P.RHO_SIZE
    t1: list[list[int]] = []
    tlen = 32 * _bitlen64(bnd)  # *bytes* per poly (FIPS: 32·bitlen b)
    for _ in range(P.K):
        t1.append(
            simple_bit_unpack(pk[rest : rest + tlen], bnd)  # type: ignore[arg-type]
        )
        rest += tlen
    return rho, t1


def sk_encode(
    rho: bytes,
    k_key: bytes,
    tr: bytes,
    s1: list[list[int]],
    s2: list[list[int]],
    t0: list[list[int]],
) -> bytes:
    sk = bytearray()
    sk.extend(rho)
    sk.extend(k_key)
    sk.extend(tr)
    for i in range(P.L):
        sk.extend(bit_pack(s1[i], P.ETA, P.ETA))
    for i in range(P.K):
        sk.extend(bit_pack(s2[i], P.ETA, P.ETA))
    t0a = (1 << (P.D - 1)) - 1
    t0b = 1 << (P.D - 1)
    for i in range(P.K):
        sk.extend(bit_pack(t0[i], t0a, t0b))
    if len(sk) != P.SK_SIZE:  # pragma: no cover
        raise RuntimeError("sk length mismatch", len(sk))
    return bytes(sk)


def sk_decode(sk: bytes) -> tuple[bytes, bytes, bytes, list[list[int]], list[list[int]], list[list[int]]]:
    if len(sk) != P.SK_SIZE:
        raise ValueError("invalid sk length")
    o = 0
    rho = sk[o : o + P.RHO_SIZE]
    o += P.RHO_SIZE
    k_key = sk[o : o + P.K_KEY_SIZE]
    o += P.K_KEY_SIZE
    tr = sk[o : o + P.TR_SIZE]
    o += P.TR_SIZE
    bls = 32 * _bitlen64(P.ETA + P.ETA)  # bytes per s1 / s2 poly
    t0a = (1 << (P.D - 1)) - 1
    t0b = 1 << (P.D - 1)
    t0len = 32 * _bitlen64(t0a + t0b)
    s1: list[list[int]] = []
    for _ in range(P.L):
        s1.append(bit_unpack(sk[o : o + bls], P.ETA, P.ETA))
        o += bls
    s2: list[list[int]] = []
    for _ in range(P.K):
        s2.append(bit_unpack(sk[o : o + bls], P.ETA, P.ETA))
        o += bls
    t0: list[list[int]] = []
    for _ in range(P.K):
        t0.append(bit_unpack(sk[o : o + t0len], t0a, t0b))
        o += t0len
    return rho, k_key, tr, s1, s2, t0


def w1_encode(w1: list[list[int]]) -> bytes:
    """FIPS 204, Algorithm 28."""
    bnd = (P.Q - 1) // (2 * P.GAMMA2) - 1
    out = bytearray()
    for i in range(P.K):
        out.extend(simple_bit_pack(w1[i], bnd))
    return bytes(out)


def sig_encode(c_tilde: bytes, z: list[list[int]], hn: list[list[int]]) -> bytes:
    """FIPS 204, Algorithm 26."""
    if len(c_tilde) != P.C_TILDE_SIZE:
        raise ValueError("c_tilde len")
    sig = bytearray(c_tilde)
    for i in range(P.L):
        sig.extend(bit_pack(z[i], P.GAMMA1 - 1, P.GAMMA1))
    sig.extend(hint_bit_pack(hn))
    if len(sig) != P.SIG_SIZE:  # pragma: no cover
        raise RuntimeError("sig size", len(sig))
    return bytes(sig)


def sig_decode(sig: bytes) -> tuple[bytes, list[list[int]], list[list[int]]] | None:
    """FIPS 204, Algorithm 27."""
    if len(sig) != P.SIG_SIZE:
        return None
    c_tilde = sig[: P.C_TILDE_SIZE]
    o = P.C_TILDE_SIZE
    zl = 32 * (1 + _bitlen64(P.GAMMA1 - 1))  # bytes per z poly
    z: list[list[int]] = []
    for _ in range(P.L):
        z.append(bit_unpack(sig[o : o + zl], P.GAMMA1 - 1, P.GAMMA1))
        o += zl
    h = hint_bit_unpack(sig[o:])
    if h is None:
        return None
    return c_tilde, z, h


# --- message formatting (Algorithm 2) ---

def message_prime_pure(ctx: bytes, msg: bytes) -> list[int]:
    """
    M' = BytesToBits( IntegerToBytes(0,1) || IntToBytes(|ctx|,1) || ctx ) || M
    (M and prefix as bits; M is the message as bits).
    """
    if len(ctx) > 255:
        raise ValueError("context too long")
    prefix = integer_to_bytes(0, 1) + integer_to_bytes(len(ctx), 1) + ctx
    b1 = bytes_to_bits(prefix)
    b2 = bytes_to_bits(msg)
    return b1 + b2


def hash_mu_tr_message(tr: bytes, mprime_bits: list[int]) -> bytes:
    """
    H(BytesToBits(tr) || M', 64) — pack full bitstring then SHAKE-256, 64 bytes.
    """
    b = bytes_to_bits(tr) + mprime_bits
    return h_bytes_p(b)


def h_bytes_p(bits: list[int]) -> bytes:
    from . import hashing

    return hashing.h_bytes(bits_to_bytes(bits), 64)


# Local alias for use in other modules
def h_bytes_mixed(trbits_mprime: bytes) -> bytes:
    """When already packed as bytes (deprecated helper)."""
    from . import hashing

    return hashing.h_bytes(trbits_mprime, 64)
