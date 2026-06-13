"""Opt-in encryption-at-rest for private key files.

When ``OMNIX_KEY_ENCRYPTION`` is truthy AND the OS keychain (``keyring``) is
available, secret key material is stored as an AES-256-GCM envelope whose
key-encryption-key (KEK) lives in the OS keychain — never on disk. Reads
transparently decrypt an envelope or pass plaintext through, so pre-existing
plaintext keys keep working and the change is fully backward compatible.

Design choices that keep this safe:

* **Opt-in / default off.** With the flag unset, ``write_secret`` writes the
  PEM in plaintext (still owner-only via ``harden_permissions``) exactly as
  before — zero behaviour change for dev, tests, and CI.
* **No lock-out.** If encryption is requested but the keychain is unavailable,
  we log a warning and fall back to plaintext rather than writing a key nobody
  can read. A genuine envelope that cannot be decrypted raises loudly (the
  operator's keychain entry was lost) instead of silently "verifying".
* **AEAD-bound.** The envelope magic is the GCM associated data, so an envelope
  cannot be replayed as a different format.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import secrets
from pathlib import Path

from .keystore import harden_permissions

log = logging.getLogger("omnix.receipts.secure_keyfile")

_MAGIC = "OMNIX-ENC-AESGCM-v1"
_SERVICE = "omnix-key-encryption"
_KEK_USER = "default-kek"


def encryption_enabled() -> bool:
    return os.environ.get("OMNIX_KEY_ENCRYPTION", "").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def _keyring():
    try:
        import keyring  # type: ignore

        return keyring
    except Exception:  # noqa: BLE001 - any import/backend failure → no keychain
        return None


def _get_or_create_kek() -> bytes | None:
    """Return the 32-byte KEK from the OS keychain, creating it on first use.

    Returns None when no keychain backend is usable.
    """
    kr = _keyring()
    if kr is None:
        return None
    try:
        existing = kr.get_password(_SERVICE, _KEK_USER)
        if existing:
            return base64.b64decode(existing)
        kek = secrets.token_bytes(32)
        kr.set_password(_SERVICE, _KEK_USER, base64.b64encode(kek).decode("ascii"))
        return kek
    except Exception:  # noqa: BLE001 - locked/again-unavailable keychain
        log.warning("OS keychain access failed; key encryption-at-rest disabled")
        return None


def _is_envelope(text: str) -> bool:
    s = text.lstrip()
    if not s.startswith("{"):
        return False
    try:
        env = json.loads(text)
    except json.JSONDecodeError:
        return False
    return isinstance(env, dict) and env.get("magic") == _MAGIC


def write_secret(path: Path | str, pem_text: str) -> None:
    """Write secret PEM *pem_text* to *path*, encrypted at rest when enabled."""
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    if encryption_enabled():
        kek = _get_or_create_kek()
        if kek is not None:
            from cryptography.hazmat.primitives.ciphers.aead import AESGCM

            nonce = os.urandom(12)
            ct = AESGCM(kek).encrypt(nonce, pem_text.encode("utf-8"), _MAGIC.encode())
            envelope = {
                "magic": _MAGIC,
                "nonce": base64.b64encode(nonce).decode("ascii"),
                "ciphertext": base64.b64encode(ct).decode("ascii"),
            }
            p.write_text(json.dumps(envelope), encoding="utf-8")
            harden_permissions(p)
            return
        log.warning(
            "OMNIX_KEY_ENCRYPTION is set but no OS keychain is available; "
            "writing %s in plaintext (owner-only) to avoid a lock-out.",
            p.name,
        )
    p.write_text(pem_text, encoding="utf-8")
    harden_permissions(p)


def read_secret(path: Path | str) -> str:
    """Read secret PEM from *path*, transparently decrypting an envelope.

    Plaintext keys (no envelope) pass through unchanged. A genuine envelope
    whose KEK is unavailable raises — that is a lost-keychain operator error,
    not a key we should silently treat as missing.
    """
    p = Path(path)
    raw = p.read_text(encoding="utf-8")
    if not _is_envelope(raw):
        return raw
    env = json.loads(raw)
    kek = _get_or_create_kek()
    if kek is None:
        raise RuntimeError(
            f"{p} is an encrypted key envelope but the OS keychain KEK is "
            "unavailable; cannot decrypt (was the keychain entry removed?)"
        )
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = base64.b64decode(env["nonce"])
    ct = base64.b64decode(env["ciphertext"])
    pt = AESGCM(kek).decrypt(nonce, ct, _MAGIC.encode())
    return pt.decode("utf-8")


def read_secret_bytes(path: Path | str) -> bytes:
    """``read_secret`` returning bytes (for callers that load PEM via bytes)."""
    return read_secret(path).encode("utf-8")
