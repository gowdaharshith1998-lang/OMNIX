"""Ed25519 signer for provenance sidecars."""

from __future__ import annotations

import base64
import json
from hashlib import sha256
from pathlib import Path
from typing import Any

from cryptography.exceptions import InvalidSignature

from omnix.receipts.finding_keys import _load_private_key, _load_public_key, ensure_project_key


def canonical_sidecar_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


class SidecarSigner:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.private_key_path, self.public_key_path, _created = ensure_project_key(self.project_root)

    def sign(self, payload_bytes: bytes) -> bytes:
        return _load_private_key(self.private_key_path).sign(payload_bytes)

    def sign_b64(self, payload: dict[str, Any]) -> str:
        return base64.b64encode(self.sign(canonical_sidecar_bytes(payload))).decode("ascii")

    @property
    def public_key_fingerprint(self) -> str:
        return sha256(self.public_key_path.read_bytes()).hexdigest()


def verify_sidecar_signature(payload: dict[str, Any], signature_b64: str, pubkey_path: Path) -> bool:
    try:
        sig = base64.b64decode(signature_b64, validate=True)
        pub = _load_public_key(pubkey_path)
        pub.verify(sig, canonical_sidecar_bytes(payload))
        return True
    except (InvalidSignature, ValueError, TypeError):
        return False
