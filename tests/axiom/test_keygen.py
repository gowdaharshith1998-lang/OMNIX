"""FIPS 204 Algorithm 6: key material sizes."""

from __future__ import annotations

import omnix.axiom.keygen as kg
import omnix.axiom.params as P


def test_keygen_internal_sizes() -> None:
    pk, sk = kg.keygen_internal(b"e" * 32)
    assert len(pk) == P.PK_SIZE
    assert len(sk) == P.SK_SIZE
