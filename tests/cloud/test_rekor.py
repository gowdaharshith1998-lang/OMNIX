"""Rekor v2 transparency-log client tests."""

from __future__ import annotations

import hashlib

import pytest

from omnix.cloud.sigstore.rekor_client import (
    FakeRekor,
    embed_inclusion,
    get_rekor,
    set_rekor,
    upload_and_embed,
)


@pytest.fixture
def rekor():
    fake = FakeRekor()
    set_rekor(fake)
    yield fake
    set_rekor(FakeRekor())


def test_submit_returns_monotonically_increasing_log_index(rekor):
    incl0 = rekor.submit(signature=b"sig0", public_key=b"pk", payload_hash="h0")
    incl1 = rekor.submit(signature=b"sig1", public_key=b"pk", payload_hash="h1")
    assert incl0.log_index == 0
    assert incl1.log_index == 1
    assert incl1.tree_size == 2


def test_verify_inclusion_round_trip(rekor):
    incl = rekor.submit(signature=b"sig", public_key=b"pk", payload_hash="abc")
    assert rekor.verify_inclusion(inclusion=incl, payload_hash="abc")


def test_verify_rejects_wrong_hash(rekor):
    incl = rekor.submit(signature=b"sig", public_key=b"pk", payload_hash="abc")
    assert not rekor.verify_inclusion(inclusion=incl, payload_hash="xyz")


def test_verify_rejects_out_of_range_index(rekor):
    incl = rekor.submit(signature=b"sig", public_key=b"pk", payload_hash="abc")
    incl.log_index = 99
    assert not rekor.verify_inclusion(inclusion=incl, payload_hash="abc")


def test_embed_inclusion_attaches_proof():
    receipt = {"id": "r1", "result": "ok"}
    from omnix.cloud.sigstore.rekor_client import RekorInclusion
    incl = RekorInclusion(log_index=0, log_id="L",
                          integrated_time=123, tree_size=1, root_hash="root",
                          inclusion_proof_hashes=["h1"], inclusion_proof_log_index=0)
    enriched = embed_inclusion(receipt, incl)
    assert enriched["rekor"]["log_index"] == 0
    assert enriched["rekor"]["root_hash"] == "root"
    assert enriched["id"] == "r1"


def test_upload_and_embed_round_trip(rekor):
    payload = b'{"id":"r","result":"ok"}'
    incl = upload_and_embed(receipt_payload=payload, signature=b"sig", public_key=b"pk")
    assert incl.log_index == 0
    assert get_rekor().verify_inclusion(
        inclusion=incl, payload_hash=hashlib.sha256(payload).hexdigest()
    )


def test_root_hash_changes_with_each_submission(rekor):
    a = rekor.submit(signature=b"s", public_key=b"p", payload_hash="A").root_hash
    b = rekor.submit(signature=b"s", public_key=b"p", payload_hash="B").root_hash
    assert a != b
