"""Tests for the ML-DSA-65 receipt signer (D1 P4)."""

from __future__ import annotations

import json

import pytest

from omnix.crypto import ml_dsa_65
from omnix.dm.receipts import ml_dsa_65_signer as signer


def test_canonicalize_is_deterministic():
    payload = {"b": 1, "a": [2, 1]}
    c1 = signer.canonicalize(payload)
    c2 = signer.canonicalize(payload)
    assert c1 == c2
    # Different key-insertion-order yields same canonical bytes
    payload2 = {"a": [2, 1], "b": 1}
    assert signer.canonicalize(payload2) == c1


def test_sign_then_verify_roundtrip():
    pk, sk = ml_dsa_65.keypair()
    payload = {"x": 1, "y": "hello"}
    canonical, sig_hex = signer.sign_canonical(payload, sk)
    assert signer.verify_canonical(payload, sig_hex, pk) is True
    # Tampering with the payload breaks verification
    assert signer.verify_canonical({"x": 1, "y": "tampered"}, sig_hex, pk) is False


def test_verify_rejects_malformed_signature():
    pk, _ = ml_dsa_65.keypair()
    assert signer.verify_canonical({"a": 1}, "not-hex", pk) is False
    assert signer.verify_canonical({"a": 1}, "abcd" * 1000, pk) is False
