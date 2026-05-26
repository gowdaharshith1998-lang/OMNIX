"""Thin sign-then-package wrapper over ``omnix.crypto.ml_dsa_65``.

The wrapper is intentionally narrow: it takes a Python dict, canonicalizes it
into bytes, and returns ``(canonical_json_bytes, signature_hex)``. Atomic
write semantics belong in the per-manifest emitter — see
``mapping_emitter`` and ``manifest_emitter``.
"""

from __future__ import annotations

import json
from typing import Tuple

from omnix.crypto import ml_dsa_65


def canonicalize(payload: dict) -> bytes:
    """Render ``payload`` as canonical UTF-8 JSON bytes (sorted keys, no whitespace)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def sign_canonical(payload: dict, secret_key: bytes) -> Tuple[bytes, str]:
    """Sign ``payload`` with ``secret_key``. Returns ``(canonical_bytes,
    signature_hex)``. Signing failure raises — callers must NOT write a file
    when this raises (the emitter pattern handles that)."""
    canonical = canonicalize(payload)
    sig = ml_dsa_65.sign(secret_key, canonical)
    return canonical, sig.hex()


def verify_canonical(payload: dict, signature_hex: str, public_key: bytes) -> bool:
    canonical = canonicalize(payload)
    try:
        sig = bytes.fromhex(signature_hex)
    except ValueError:
        return False
    return ml_dsa_65.verify(public_key, canonical, sig)


__all__ = [
    "canonicalize",
    "sign_canonical",
    "verify_canonical",
]
