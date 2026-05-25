"""Tests for the Rekor onboarding CLI and audit-kit inclusion-proof round-trip."""

from __future__ import annotations

import base64
import io
import json
import tarfile
from pathlib import Path

import pytest

from omnix.cloud.audit.kit import AuditEvidence, AuditKit, export_kit
from omnix.cloud.sigstore.onboarding import (
    compute_fingerprint,
    generate_signing_key,
    render_secret_manifest,
)
from omnix.cloud.sigstore.rekor_client import (
    FakeRekor,
    embed_inclusion,
    upload_and_embed,
    get_rekor,
    set_rekor,
)


def test_generate_signing_key_has_pem_headers() -> None:
    key = generate_signing_key()
    assert "-----BEGIN" in key.private_key_pem
    assert "-----END" in key.private_key_pem
    assert "PUBLIC KEY" in key.public_key_pem


def test_compute_fingerprint_is_sha256_hex() -> None:
    fingerprint = compute_fingerprint(b"\x30\x59\x30\x13\x06\x07")
    assert len(fingerprint) == 64
    int(fingerprint, 16)  # raises ValueError if not hex


def test_compute_fingerprint_stable_for_same_input() -> None:
    der = b"\x30\x59\x30\x13\x06\x07test-input"
    assert compute_fingerprint(der) == compute_fingerprint(der)


def test_render_secret_manifest_has_required_keys() -> None:
    key = generate_signing_key()
    manifest_json = render_secret_manifest(
        name="omnix-rekor-signing", namespace="omnix", signing_key=key
    )
    parsed = json.loads(manifest_json)
    assert parsed["kind"] == "Secret"
    assert parsed["metadata"]["name"] == "omnix-rekor-signing"
    assert parsed["metadata"]["namespace"] == "omnix"
    data = parsed["data"]
    assert "rekor-signing.pem" in data
    assert "rekor-public.pem" in data
    assert "fingerprint.txt" in data
    decoded_fp = base64.b64decode(data["fingerprint.txt"]).decode()
    assert decoded_fp == key.fingerprint_sha256


def test_render_secret_manifest_omits_namespace_when_none() -> None:
    key = generate_signing_key()
    manifest = json.loads(render_secret_manifest(
        name="omnix-rekor-signing", namespace=None, signing_key=key
    ))
    assert "namespace" not in manifest["metadata"]


def test_embed_inclusion_round_trips_through_audit_kit(tmp_path: Path) -> None:
    """End-to-end: FakeRekor submission → audit kit bundle → verify proof structure."""
    rekor = FakeRekor()
    set_rekor(rekor)
    try:
        receipt_payload = b'{"unit":"checkout","percentage":25}'
        inclusion = upload_and_embed(
            receipt_payload=receipt_payload,
            signature=b"toy-sig",
            public_key=b"toy-pk",
        )
        receipt_dict = {"unit": "checkout", "percentage": 25}
        embedded = embed_inclusion(receipt_dict, inclusion)
        assert embedded["rekor"]["log_index"] == 0
        assert "root_hash" in embedded["rekor"]

        kit = AuditKit(
            customer="acme", tenant_id="t1",
            evidence=[AuditEvidence(
                receipt_id="rcpt-0001",
                payload_canonical=receipt_payload,
                signature=b"toy-sig",
                public_key=b"toy-pk",
                rekor_inclusion=embedded["rekor"],
            )],
            generated_at="2026-05-25T00:00:00Z",
        )
        out = tmp_path / "kit.tar.gz"
        summary = export_kit(kit, out)
        assert summary["receipts"] == 1
        assert out.exists()

        # Round-trip: open the tarball, confirm the rekor proof is present
        with tarfile.open(out) as tf:
            names = tf.getnames()
            assert "rekor/rcpt-0001.proof.json" in names
            proof_member = tf.extractfile("rekor/rcpt-0001.proof.json")
            assert proof_member is not None
            proof = json.loads(proof_member.read().decode())
            assert proof["log_index"] == 0
            assert proof["root_hash"] == inclusion.root_hash
    finally:
        # Restore the module-level fake rekor.
        set_rekor(FakeRekor())


def test_two_receipts_share_consistent_tree_root(tmp_path: Path) -> None:
    """When two receipts are uploaded, the second inclusion's tree_size matches
    the second submission and the root_hash advances."""
    rekor = FakeRekor()
    set_rekor(rekor)
    try:
        inc1 = upload_and_embed(receipt_payload=b"r1", signature=b"s1", public_key=b"p")
        inc2 = upload_and_embed(receipt_payload=b"r2", signature=b"s2", public_key=b"p")
        assert inc1.tree_size == 1
        assert inc2.tree_size == 2
        assert inc1.root_hash != inc2.root_hash
    finally:
        set_rekor(FakeRekor())
