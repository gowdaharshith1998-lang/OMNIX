"""ML-DSA-65 receipt: canonical JSON and signature verification."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from omnix.axiom import keystore
from omnix.verify import receipt


def test_canonical_json() -> None:
    body = {
        "version": 1,
        "kind": "verify",
        "z": 2,
        "a": 0,
    }
    raw, _b64 = receipt.split_payload_for_signing({**body})
    s = json.dumps(
        {k: v for k, v in body.items()},
        sort_keys=True,
        separators=(",", ":"),
    )
    assert raw == s.encode("utf-8")


@pytest.fixture
def keypair_dir(tmp_path: Path) -> Path:
    d = tmp_path / "k"
    keystore.write_keypair_dir(d)
    return d


def test_sign_and_verify(keypair_dir: Path) -> None:
    b: dict = {
        "version": 1,
        "kind": "verify",
        "examples_run": 0,
    }
    r = receipt.mint_signed_receipt(
        b, secret_pem_path=keypair_dir / "secret.pem"
    )
    d = json.loads(r) if isinstance(r, str) else r
    assert "axiom_signature" in d
    assert receipt.verify_signature(
        d, public_key_path=keypair_dir / "public.pem"
    )


def test_tamper_fails(keypair_dir: Path) -> None:
    b = {
        "version": 1,
        "kind": "verify",
        "examples_run": 1,
    }
    s = receipt.mint_signed_receipt(
        b, secret_pem_path=keypair_dir / "secret.pem"
    )
    d = json.loads(s) if isinstance(s, str) else s
    d2 = {**d, "examples_run": 99}
    assert not receipt.verify_signature(
        d2, public_key_path=keypair_dir / "public.pem"
    )
