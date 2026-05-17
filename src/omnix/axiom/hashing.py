# Compliance: P11, P20 — H/G use only SHAKE-128/256 (FIPS 204 §3.7)
"""FIPS 204 §3.7: H = SHAKE256, G = SHAKE128."""

from __future__ import annotations

import hashlib


def h_bytes(data: bytes, n_bytes: int) -> bytes:
    """
    FIPS 204: H(str, L) = SHAKE256(str, 8*L) with byte string input.
    """
    return hashlib.shake_256(data).digest(n_bytes)


def g_bytes(data: bytes, n_bytes: int) -> bytes:
    """FIPS 204: G(str, L) = SHAKE128(str, 8*L)."""
    return hashlib.shake_128(data).digest(n_bytes)
