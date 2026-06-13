"""Encryption-at-rest for secret key files (opt-in, keychain-backed)."""

from __future__ import annotations

import base64
import json
from pathlib import Path

import pytest

from omnix.receipts import secure_keyfile as sk

_PEM = "-----BEGIN TEST KEY-----\nZm9vYmFy\n-----END TEST KEY-----\n"


class _FakeKeyring:
    def __init__(self) -> None:
        self._store: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, user: str) -> str | None:
        return self._store.get((service, user))

    def set_password(self, service: str, user: str, value: str) -> None:
        self._store[(service, user)] = value


def test_default_off_writes_plaintext(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OMNIX_KEY_ENCRYPTION", raising=False)
    p = tmp_path / "k.pem"
    sk.write_secret(p, _PEM)
    assert p.read_text(encoding="utf-8") == _PEM  # plaintext on disk
    assert sk.read_secret(p) == _PEM


def test_encrypted_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIX_KEY_ENCRYPTION", "1")
    fake = _FakeKeyring()
    monkeypatch.setattr(sk, "_keyring", lambda: fake)
    p = tmp_path / "k.pem"
    sk.write_secret(p, _PEM)

    on_disk = p.read_text(encoding="utf-8")
    assert on_disk != _PEM
    env = json.loads(on_disk)
    assert env["magic"] == sk._MAGIC
    assert _PEM.encode("utf-8") not in base64.b64decode(env["ciphertext"])  # actually encrypted

    assert sk.read_secret(p) == _PEM  # transparent decrypt


def test_encryption_requested_but_no_keychain_falls_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("OMNIX_KEY_ENCRYPTION", "1")
    monkeypatch.setattr(sk, "_keyring", lambda: None)  # no keychain
    p = tmp_path / "k.pem"
    sk.write_secret(p, _PEM)
    # No lock-out: written plaintext, still readable.
    assert p.read_text(encoding="utf-8") == _PEM
    assert sk.read_secret(p) == _PEM


def test_plaintext_passthrough_on_read(tmp_path: Path) -> None:
    p = tmp_path / "k.pem"
    p.write_text(_PEM, encoding="utf-8")
    assert sk.read_secret(p) == _PEM


def test_encrypted_project_key_still_signs_and_verifies(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End-to-end: with encryption on, the Ed25519 project key is written as an
    envelope, yet sign_finding/verify_finding still round-trip (transparent
    decrypt on load)."""
    monkeypatch.setenv("OMNIX_KEY_ENCRYPTION", "1")
    monkeypatch.setenv("HOME", str(tmp_path))
    fake = _FakeKeyring()
    monkeypatch.setattr(sk, "_keyring", lambda: fake)

    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

    from omnix.receipts.finding_keys import (
        _load_private_key,
        ensure_project_key,
        project_privkey_path,
    )
    from omnix.receipts.finding_receipt import compute_project_id

    proj = tmp_path / "proj"
    proj.mkdir()
    ensure_project_key(proj.resolve())
    pid = compute_project_id(proj.resolve())

    # The private key on disk is an encrypted envelope, not a PEM.
    priv_path = project_privkey_path(pid)
    priv_disk = priv_path.read_text(encoding="utf-8")
    assert sk._is_envelope(priv_disk)
    assert "BEGIN" not in priv_disk

    # ...yet the signing path loads it transparently (decrypt-on-load) and gets
    # a usable Ed25519 private key. A round-trip sign/verify confirms it.
    priv = _load_private_key(priv_path)
    assert isinstance(priv, Ed25519PrivateKey)
    sig = priv.sign(b"omnix-e2e")
    priv.public_key().verify(sig, b"omnix-e2e")  # raises if the key is wrong


def test_envelope_without_kek_raises(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OMNIX_KEY_ENCRYPTION", "1")
    fake = _FakeKeyring()
    monkeypatch.setattr(sk, "_keyring", lambda: fake)
    p = tmp_path / "k.pem"
    sk.write_secret(p, _PEM)
    # Keychain entry lost → cannot decrypt → loud error (not silent).
    monkeypatch.setattr(sk, "_keyring", lambda: None)
    with pytest.raises(RuntimeError, match="cannot decrypt"):
        sk.read_secret(p)
