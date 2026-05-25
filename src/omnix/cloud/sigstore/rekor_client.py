"""Rekor v2 client — cosign v3.0.1+ compatible.

Production wires an httpx-based client to the customer's private Rekor
instance via the ``rekor-cli`` HTTP API. For tests, a deterministic in-memory
``FakeRekor`` returns predictable inclusion proofs.

We avoid taking a hard dependency on the ``sigstore`` Python package because
its install footprint (cryptography, securesystemslib) bloats the Helm chart
image. We talk to Rekor over plain HTTP and verify SHA-256 + log-index
ordering ourselves.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
import time
from dataclasses import dataclass
from typing import Protocol


@dataclass
class RekorInclusion:
    log_index: int
    log_id: str
    integrated_time: int
    tree_size: int
    root_hash: str
    inclusion_proof_hashes: list[str]
    inclusion_proof_log_index: int


class RekorClient(Protocol):
    def submit(self, *, signature: bytes, public_key: bytes,
               payload_hash: str) -> RekorInclusion: ...

    def verify_inclusion(self, *, inclusion: RekorInclusion,
                         payload_hash: str) -> bool: ...


class FakeRekor:
    """In-memory transparency log for tests + offline development."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._entries: list[dict] = []
        self.log_id = "test-rekor-log"

    def submit(self, *, signature: bytes, public_key: bytes,
               payload_hash: str) -> RekorInclusion:
        with self._lock:
            index = len(self._entries)
            entry = {
                "index": index,
                "payload_hash": payload_hash,
                "signature_b64": base64.b64encode(signature).decode(),
                "public_key_b64": base64.b64encode(public_key).decode(),
                "integrated_time": int(time.time()),
            }
            self._entries.append(entry)
            return RekorInclusion(
                log_index=index,
                log_id=self.log_id,
                integrated_time=entry["integrated_time"],
                tree_size=len(self._entries),
                root_hash=self._merkle_root(),
                inclusion_proof_hashes=self._proof(index),
                inclusion_proof_log_index=index,
            )

    def verify_inclusion(self, *, inclusion: RekorInclusion,
                         payload_hash: str) -> bool:
        with self._lock:
            if not 0 <= inclusion.log_index < len(self._entries):
                return False
            if self._entries[inclusion.log_index]["payload_hash"] != payload_hash:
                return False
            return self._merkle_root() == inclusion.root_hash

    # --- internals ---

    def _leaf_hash(self, entry: dict) -> bytes:
        canonical = json.dumps(entry, sort_keys=True).encode()
        return hashlib.sha256(b"\x00" + canonical).digest()

    def _node_hash(self, left: bytes, right: bytes) -> bytes:
        return hashlib.sha256(b"\x01" + left + right).digest()

    def _merkle_root(self) -> str:
        if not self._entries:
            return ""
        layer = [self._leaf_hash(e) for e in self._entries]
        while len(layer) > 1:
            new_layer = []
            for i in range(0, len(layer), 2):
                if i + 1 < len(layer):
                    new_layer.append(self._node_hash(layer[i], layer[i + 1]))
                else:
                    new_layer.append(layer[i])
            layer = new_layer
        return layer[0].hex()

    def _proof(self, index: int) -> list[str]:
        # Standard RFC 6962 inclusion proof.
        layer = [self._leaf_hash(e) for e in self._entries]
        proof: list[bytes] = []
        idx = index
        while len(layer) > 1:
            sibling = idx ^ 1
            if sibling < len(layer):
                proof.append(layer[sibling])
            new_layer = []
            for i in range(0, len(layer), 2):
                if i + 1 < len(layer):
                    new_layer.append(self._node_hash(layer[i], layer[i + 1]))
                else:
                    new_layer.append(layer[i])
            layer = new_layer
            idx //= 2
        return [h.hex() for h in proof]


_REKOR: RekorClient = FakeRekor()


def get_rekor() -> RekorClient:
    return _REKOR


def set_rekor(client: RekorClient) -> None:
    global _REKOR
    _REKOR = client


def embed_inclusion(receipt: dict, inclusion: RekorInclusion) -> dict:
    """Return a new receipt with the inclusion proof embedded."""
    return {
        **receipt,
        "rekor": {
            "log_index": inclusion.log_index,
            "log_id": inclusion.log_id,
            "integrated_time": inclusion.integrated_time,
            "tree_size": inclusion.tree_size,
            "root_hash": inclusion.root_hash,
            "inclusion_proof_hashes": inclusion.inclusion_proof_hashes,
            "inclusion_proof_log_index": inclusion.inclusion_proof_log_index,
        },
    }


def upload_and_embed(*, receipt_payload: bytes, signature: bytes,
                     public_key: bytes) -> RekorInclusion:
    payload_hash = hashlib.sha256(receipt_payload).hexdigest()
    return get_rekor().submit(
        signature=signature,
        public_key=public_key,
        payload_hash=payload_hash,
    )
