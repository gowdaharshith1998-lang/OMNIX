"""Merkle tree helpers for scan manifests."""

from __future__ import annotations

import hashlib
import time

from omnix.axiom.merkle import (
    EMPTY_SENTINEL,
    compute_leaf_hash,
    compute_merkle_root,
    merkle_proof,
    verify_inclusion,
)


def test_empty_returns_sentinel() -> None:
    assert compute_merkle_root([]) == hashlib.sha256(EMPTY_SENTINEL).hexdigest()


def test_single_leaf_returns_digest_hex() -> None:
    h = hashlib.sha256(b"x").digest()
    assert compute_merkle_root([h]) == h.hex()


def test_two_leaves_combines_correctly() -> None:
    a = hashlib.sha256(b"a").digest()
    b = hashlib.sha256(b"b").digest()
    expected = hashlib.sha256(a + b).hexdigest()
    assert compute_merkle_root([a, b]) == expected


def test_odd_leaves_duplicate_last() -> None:
    a = hashlib.sha256(b"1").digest()
    b = hashlib.sha256(b"2").digest()
    c = hashlib.sha256(b"3").digest()
    ab = hashlib.sha256(a + b).digest()
    cc = hashlib.sha256(c + c).digest()
    root = hashlib.sha256(ab + cc).hexdigest()
    assert compute_merkle_root([a, b, c]) == root


def test_deterministic_same_input_same_root() -> None:
    xs = [hashlib.sha256(bytes([i])).digest() for i in range(5)]
    assert compute_merkle_root(xs) == compute_merkle_root(xs)


def test_different_orders_different_roots() -> None:
    a = hashlib.sha256(b"a").digest()
    b = hashlib.sha256(b"b").digest()
    assert compute_merkle_root([a, b]) != compute_merkle_root([b, a])


def test_inclusion_proof_valid_leaf_returns_true() -> None:
    leaves = [
        hashlib.sha256(b"a").digest(),
        hashlib.sha256(b"b").digest(),
        hashlib.sha256(b"c").digest(),
    ]
    leaves_sorted = sorted(leaves)
    root = compute_merkle_root(leaves_sorted)
    for i, leaf in enumerate(leaves_sorted):
        proof = merkle_proof(leaves_sorted, i)
        assert verify_inclusion(leaf, proof, root)


def test_inclusion_proof_wrong_leaf_returns_false() -> None:
    leaves = [hashlib.sha256(bytes([i])).digest() for i in range(4)]
    root = compute_merkle_root(leaves)
    bad = hashlib.sha256(b"nope").digest()
    proof = merkle_proof(leaves, 0)
    assert not verify_inclusion(bad, proof, root)


def test_large_tree_1000_leaves() -> None:
    leaves = [hashlib.sha256(bytes([i % 256, i >> 8])).digest() for i in range(1000)]
    t0 = time.perf_counter()
    _ = compute_merkle_root(leaves)
    assert time.perf_counter() - t0 < 0.5


def test_inclusion_proof_single_leaf_empty_proof() -> None:
    leaf = hashlib.sha256(b"only").digest()
    root = compute_merkle_root([leaf])
    assert verify_inclusion(leaf, [], root)


def test_compute_leaf_hash_matches_sha256_of_payload() -> None:
    b = b'{"a":1}'
    assert compute_leaf_hash(b) == hashlib.sha256(b).digest()
