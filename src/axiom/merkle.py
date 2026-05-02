# Compliance: P17 (no mutable default args in AXIOM modules).
"""Deterministic Merkle tree over finding-receipt leaf hashes (slice 18d).

Odd-sized levels duplicate the last node (RFC 6962 / Bitcoin-style) so the
tree is well-defined for any leaf count.
"""

from __future__ import annotations

import hashlib

EMPTY_SENTINEL = b"omnix_empty_scan"


def compute_leaf_hash(canonical_bytes: bytes) -> bytes:
    """SHA-256 digest of one canonical-JSON receipt payload (32 bytes)."""
    return hashlib.sha256(canonical_bytes).digest()


def compute_merkle_root(leaves: list[bytes]) -> str:
    """Bottom-up Merkle root. Returns 64-char lowercase hex.

    - Empty ``leaves`` → ``sha256(EMPTY_SENTINEL).hexdigest()``.
    - ``leaves`` must be pre-sorted by the caller (e.g. by ``finding_id``);
      this function does not reorder.
    - Pair hash: ``sha256(left || right)`` over raw 32-byte digests.
    - Odd count at a level: duplicate the last node when pairing.
    """
    if not leaves:
        return hashlib.sha256(EMPTY_SENTINEL).hexdigest()

    level = list(leaves)
    while len(level) > 1:
        nxt: list[bytes] = []
        i = 0
        while i < len(level):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else level[i]
            nxt.append(hashlib.sha256(left + right).digest())
            i += 2
        level = nxt
    return level[0].hex()


def verify_inclusion(
    leaf: bytes,
    proof: list[tuple[bytes, str]],
    expected_root_hex: str,
) -> bool:
    """Verify ``leaf`` reaches ``expected_root_hex`` given ``proof``.

    ``proof`` is ``(sibling_digest_32_bytes, side)`` from leaf toward root,
    where ``side`` is ``'L'`` if sibling is left of current, ``'R'`` if right.
    """
    current = leaf
    for sibling, side in proof:
        if side == "L":
            current = hashlib.sha256(sibling + current).digest()
        elif side == "R":
            current = hashlib.sha256(current + sibling).digest()
        else:
            return False
    return current.hex() == expected_root_hex


def merkle_proof(leaves: list[bytes], leaf_index: int) -> list[tuple[bytes, str]]:
    """Build inclusion proof for sorted leaf list (testing / future CLI)."""
    if not leaves or leaf_index < 0 or leaf_index >= len(leaves):
        return []
    level = list(leaves)
    idx = leaf_index
    proof: list[tuple[bytes, str]] = []
    while len(level) > 1:
        if idx % 2 == 0:
            sibling_i = idx + 1 if idx + 1 < len(level) else idx
            side = "R"
        else:
            sibling_i = idx - 1
            side = "L"
        proof.append((level[sibling_i], side))
        nxt: list[bytes] = []
        i = 0
        while i < len(level):
            left = level[i]
            right = level[i + 1] if i + 1 < len(level) else level[i]
            nxt.append(hashlib.sha256(left + right).digest())
            i += 2
        idx //= 2
        level = nxt
    return proof
