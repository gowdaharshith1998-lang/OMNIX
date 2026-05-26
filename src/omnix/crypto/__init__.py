"""OMNIX crypto primitives — thin, audit-friendly wrappers over vetted libraries.

ML-DSA-65 (FIPS 204) is the canonical signing primitive for all OMNIX-DM receipts.
See ``omnix.crypto.ml_dsa_65`` for the public ``sign`` / ``verify`` / ``keypair`` API.
"""

from omnix.crypto import ml_dsa_65

__all__ = ["ml_dsa_65"]
