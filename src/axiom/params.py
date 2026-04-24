"""ML-DSA-65 (FIPS 204 parameter set 3) constants."""

# Compliance: P11, P12, P15, P16, P20 — no md5/sha1/hash(); ML-DSA-65 only; no JSON key serialization.

# NIST FIPS 204, Table 1 — ML-DSA-65
Q: int = 8380417
N: int = 256
D: int = 13
TAU: int = 49
GAMMA1: int = 524_288  # 2^19
GAMMA2: int = (Q - 1) // 32
K: int = 6
L: int = 5
ETA: int = 4
BETA: int = TAU * ETA
OMEGA: int = 55
LMBDA: int = 192  # collision strength for c_tilde; λ/4 byte length

# Key / signature byte lengths (FIPS 204, Table 2)
PK_SIZE: int = 1952
SK_SIZE: int = 4032
SIG_SIZE: int = 3309

# Domain seeds (FIPS 204 §3.7, Algorithm 6)
RHO_SIZE: int = 32
RHO_PRIME_SIZE: int = 64
K_KEY_SIZE: int = 32
TR_SIZE: int = 64
SEED_E_SIZE: int = 32  # ξ for KeyGen_internal

# Challenge / commitment sizes
C_TILDE_SIZE: int = LMBDA // 4  # 48 bytes
RND_SIZE: int = 32  # hedged / deterministic

# T_1 / packing (bitlen(Q-1) = 23, 23 - D = 10)
T1_BITLEN: int = 23 - D

# Coefficient bounds
Z_POL_BYTELEN: int = 32 * (1 + 19)  # sig encoding: 32 * (1 + bitlen(γ1-1)) when γ1 = 2^19

# NTT: 256^{-1} mod Q (FIPS 204, Algorithm 42, line 21)
F: int = 8_347_681

# Root of unity (FIPS 204, §2.5)
ZETA: int = 1753
