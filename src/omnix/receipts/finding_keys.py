# Compliance: P17 (no mutable default args in AXIOM modules).
"""Ed25519 project keys and sign/verify for per-finding receipts (slice 18d).

Coexists with ML-DSA-65 in ``axiom.keystore`` / ``axiom.sign`` (evolution receipts).
"""

from __future__ import annotations

import base64
import os
from pathlib import Path

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import (
    Ed25519PrivateKey,
    Ed25519PublicKey,
)

from .finding_receipt import FindingReceipt
from .keystore import harden_permissions


class InvalidFindingPublicKeyError(ValueError):
    """PEM at ``pubkey_path`` is missing, corrupted, or not an Ed25519 public key."""


def omnix_home() -> Path:
    raw = os.environ.get("OMNIX_HOME") or os.environ.get("HOME")
    if raw:
        return Path(raw).expanduser()
    return Path.home()


def global_keys_dir() -> Path:
    return omnix_home() / ".omnix" / "keys"


def project_pubkey_path(project_root: Path) -> Path:
    return project_root / ".omnix" / "pubkey.pem"


def project_privkey_path(project_id: str) -> Path:
    return global_keys_dir() / f"{project_id}.pem"


def ensure_project_key(project_root: Path) -> tuple[Path, Path, bool]:
    """Generate Ed25519 keypair if absent. Idempotent.

    Returns (private_key_path, public_key_path, was_created).
    """
    project_root = project_root.resolve(strict=True)
    from .finding_receipt import compute_project_id

    project_id = compute_project_id(project_root)
    priv_path = project_privkey_path(project_id)
    pub_path = project_pubkey_path(project_root)

    keys_dir = global_keys_dir()
    keys_dir.mkdir(parents=True, exist_ok=True)
    os.chmod(keys_dir, 0o700)

    project_omnix_dir = project_root / ".omnix"
    project_omnix_dir.mkdir(parents=True, exist_ok=True)

    if priv_path.is_file():
        priv = _load_private_key(priv_path)
        expected_pub_pem = priv.public_key().public_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PublicFormat.SubjectPublicKeyInfo,
        )
        if not pub_path.exists() or pub_path.read_bytes() != expected_pub_pem:
            pub_path.write_bytes(expected_pub_pem)
        return priv_path, pub_path, False

    priv = Ed25519PrivateKey.generate()
    priv_pem = priv.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    pub_pem = priv.public_key().public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )
    priv_path.write_bytes(priv_pem)
    harden_permissions(priv_path)
    pub_path.write_bytes(pub_pem)
    return priv_path, pub_path, True


def _load_private_key(priv_path: Path) -> Ed25519PrivateKey:
    pem = priv_path.read_bytes()
    key = serialization.load_pem_private_key(pem, password=None)
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError(f"key at {priv_path} is not Ed25519")
    return key


def _load_public_key(pub_path: Path) -> Ed25519PublicKey:
    if not pub_path.is_file():
        raise FileNotFoundError(f"public key not found at {pub_path}")
    pem = pub_path.read_bytes()
    try:
        key = serialization.load_pem_public_key(pem)
    except ValueError as e:
        raise InvalidFindingPublicKeyError(
            f"invalid or corrupted public key PEM at {pub_path}: {e}"
        ) from e
    if not isinstance(key, Ed25519PublicKey):
        raise InvalidFindingPublicKeyError(
            f"key at {pub_path} is not an Ed25519 public key"
        )
    return key


def sign_finding(payload: dict, project_id: str) -> str:
    """Sign a finding receipt payload. Returns standard base64 (RFC 4648) ASCII string."""
    priv_path = project_privkey_path(project_id)
    if not priv_path.is_file():
        raise FileNotFoundError(
            f"no project key at {priv_path}; run `omnix axiom keygen` first."
        )
    receipt = FindingReceipt.from_dict(payload)
    priv = _load_private_key(priv_path)
    sig = priv.sign(receipt.canonical_json())
    return base64.b64encode(sig).decode("ascii")


def verify_finding(payload: dict, signature_b64: str, pubkey_path: Path) -> bool:
    """Verify detached Ed25519 signature. Returns False on mismatch (never raises for bad sig)."""
    try:
        pub = _load_public_key(pubkey_path)
    except FileNotFoundError:
        raise
    except InvalidFindingPublicKeyError:
        raise
    try:
        sig = base64.b64decode(signature_b64, validate=True)
    except Exception:
        return False
    try:
        receipt = FindingReceipt.from_dict(payload)
    except ValueError:
        return False
    try:
        pub.verify(sig, receipt.canonical_json())
        return True
    except InvalidSignature:
        return False
