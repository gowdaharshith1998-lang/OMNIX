"""ML-DSA-65 (FIPS 204) signing wrapper for OMNIX-DM receipts.

Backed by ``dilithium-py`` (pure-Python FIPS 204 implementation, package
``dilithium_py``). Exposes a deterministic, framework-agnostic public surface:

    pk, sk = keypair(seed=None)         # (1952-byte pk, 4032-byte sk)
    signature = sign(sk, message_bytes) # 3309-byte signature
    verify(pk, message_bytes, signature) -> bool

The wrapper is intentionally minimal — no key storage, no serialization opinions.
Callers above (the DM receipt emitters) own canonicalization and atomic writes.
"""

from __future__ import annotations

from typing import Optional, Tuple

from dilithium_py.ml_dsa import ML_DSA_65 as _ML_DSA_65

# FIPS 204 ML-DSA-65 byte sizes — exported as named constants so callers can
# pre-allocate / sanity-check without re-deriving from FIPS internals.
PUBLIC_KEY_BYTES = 1952
SECRET_KEY_BYTES = 4032
SIGNATURE_BYTES = 3309
ALGORITHM_OID = "2.16.840.1.101.3.4.3.18"  # FIPS 204 ML-DSA-65


class SigningError(RuntimeError):
    """Raised when signing or verification cannot proceed (never on bad verify)."""


def keypair(seed: Optional[bytes] = None) -> Tuple[bytes, bytes]:
    """Return ``(public_key, secret_key)``. If ``seed`` is given it is used as
    the DRBG seed for deterministic key generation (test fixtures only — never
    in production).

    Seeding is strictly scoped to this one keygen call: ``dilithium_py`` keeps
    its entropy source on the process-global ``_ML_DSA_65`` singleton, so a
    naive ``set_drbg_seed`` would leave EVERY later ``keygen``/``sign`` drawing
    from a deterministic stream — order-dependent signatures and a catastrophic
    loss of nonce entropy for a security product. We therefore snapshot the
    live entropy source, seed, generate, and restore os.urandom in ``finally``.
    """
    saved_random_bytes = getattr(_ML_DSA_65, "random_bytes", None)
    saved_drbg = getattr(_ML_DSA_65, "_drbg", None)
    try:
        if seed is not None:
            if not isinstance(seed, (bytes, bytearray)):
                raise SigningError("seed must be bytes")
            if len(seed) != 48:
                raise SigningError(f"seed must be exactly 48 bytes, got {len(seed)}")
            _ML_DSA_65.set_drbg_seed(bytes(seed))
        pk, sk = _ML_DSA_65.keygen()
    finally:
        if seed is not None:
            # Restore the pre-seed entropy source (os.urandom in production) so
            # signing and later keygens are never deterministic.
            if saved_random_bytes is not None:
                _ML_DSA_65.random_bytes = saved_random_bytes
            else:  # pragma: no cover - defensive
                import os as _os

                _ML_DSA_65.random_bytes = lambda n, _u=_os.urandom: _u(n)
            if saved_drbg is not None:
                _ML_DSA_65._drbg = saved_drbg
            elif hasattr(_ML_DSA_65, "_drbg"):
                _ML_DSA_65._drbg = None
    if len(pk) != PUBLIC_KEY_BYTES or len(sk) != SECRET_KEY_BYTES:
        raise SigningError("keygen returned unexpected size — refusing to proceed")
    return pk, sk


def sign(secret_key: bytes, message: bytes) -> bytes:
    """Sign ``message`` with ``secret_key``. Returns a 3309-byte signature."""
    if not isinstance(secret_key, (bytes, bytearray)):
        raise SigningError("secret_key must be bytes")
    if len(secret_key) != SECRET_KEY_BYTES:
        raise SigningError(
            f"secret_key must be {SECRET_KEY_BYTES} bytes, got {len(secret_key)}"
        )
    if not isinstance(message, (bytes, bytearray)):
        raise SigningError("message must be bytes")
    sig = _ML_DSA_65.sign(bytes(secret_key), bytes(message))
    if len(sig) != SIGNATURE_BYTES:
        raise SigningError(
            f"signature size unexpected: {len(sig)} != {SIGNATURE_BYTES}"
        )
    return sig


def verify(public_key: bytes, message: bytes, signature: bytes) -> bool:
    """Return True iff ``signature`` is a valid ML-DSA-65 signature of
    ``message`` under ``public_key``. Never raises on bad input — returns False
    so that callers can treat verification as a pure boolean predicate."""
    try:
        if (
            not isinstance(public_key, (bytes, bytearray))
            or len(public_key) != PUBLIC_KEY_BYTES
        ):
            return False
        if not isinstance(message, (bytes, bytearray)):
            return False
        if (
            not isinstance(signature, (bytes, bytearray))
            or len(signature) != SIGNATURE_BYTES
        ):
            return False
        return bool(
            _ML_DSA_65.verify(bytes(public_key), bytes(message), bytes(signature))
        )
    except Exception:
        return False


def fingerprint(public_key: bytes) -> str:
    """Short, stable, hex SHA-256 prefix of a public key — useful for receipt
    headers so a verifier can locate the right public key without parsing
    the full pk blob."""
    import hashlib

    return hashlib.sha256(public_key).hexdigest()[:16]


__all__ = [
    "PUBLIC_KEY_BYTES",
    "SECRET_KEY_BYTES",
    "SIGNATURE_BYTES",
    "ALGORITHM_OID",
    "SigningError",
    "keypair",
    "sign",
    "verify",
    "fingerprint",
]
