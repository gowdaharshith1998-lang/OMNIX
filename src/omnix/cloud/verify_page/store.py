"""Backing store for the public verifier.

In production this reads from the Receipt table. For tests and the local
dev server we use an in-memory store that callers populate explicitly.
"""

from __future__ import annotations

import threading
from dataclasses import dataclass


@dataclass
class ReceiptDescriptor:
    receipt_id: str
    job_id: str
    receipt_kind: str
    payload: dict
    payload_canonical: bytes
    payload_sha256: str
    signature: bytes
    public_key: bytes
    created_at: str


class ReceiptStore:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._store: dict[str, ReceiptDescriptor] = {}

    def put(self, desc: ReceiptDescriptor) -> None:
        with self._lock:
            self._store[desc.receipt_id] = desc

    def get(self, receipt_id: str) -> ReceiptDescriptor | None:
        with self._lock:
            return self._store.get(receipt_id)

    def clear(self) -> None:
        with self._lock:
            self._store.clear()


_STORE = ReceiptStore()


def get_receipt_store() -> ReceiptStore:
    return _STORE
