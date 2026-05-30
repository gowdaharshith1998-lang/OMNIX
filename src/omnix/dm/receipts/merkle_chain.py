"""Merkle-chain helpers for OMNIX-DM signed manifests.

Each manifest's canonical SHA-256 becomes the predecessor hash of the next
manifest in the chain. The genesis predecessor for a brand-new migration is
either ``None`` or the literal string ``"GENESIS"``.
"""

from __future__ import annotations

import hashlib
from typing import Optional

GENESIS_SENTINEL = "GENESIS"


def canonical_sha256_hex(canonical_bytes: bytes) -> str:
    """SHA-256 hex digest of canonical JSON bytes."""
    return hashlib.sha256(canonical_bytes).hexdigest()


def next_hash(predecessor_hash: Optional[str], current_canonical: bytes) -> str:
    """Compute the link hash for the next manifest. The link is the SHA-256 of
    ``(predecessor_hash or 'GENESIS') ++ current_canonical`` so any
    re-ordering or substitution is detectable."""
    pred = predecessor_hash if predecessor_hash else GENESIS_SENTINEL
    h = hashlib.sha256()
    h.update(pred.encode("utf-8"))
    h.update(current_canonical)
    return h.hexdigest()


__all__ = [
    "GENESIS_SENTINEL",
    "canonical_sha256_hex",
    "next_hash",
]
