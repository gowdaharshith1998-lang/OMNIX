"""Tests for the Merkle chain helper (D1 P4 / D2 P7)."""

from __future__ import annotations

from omnix.dm.receipts import merkle_chain


def test_genesis_link():
    h = merkle_chain.next_hash(None, b"first payload")
    h2 = merkle_chain.next_hash("GENESIS", b"first payload")
    assert h == h2
    assert len(h) == 64


def test_link_depends_on_predecessor():
    h_a = merkle_chain.next_hash(None, b"same body")
    h_b = merkle_chain.next_hash("some-prior-hash", b"same body")
    assert h_a != h_b


def test_canonical_sha256_hex():
    assert merkle_chain.canonical_sha256_hex(b"") == (
        "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
    )
