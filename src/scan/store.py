# Compliance: P11, P19

"""
In-memory TTL store for one-time scan detections (plaintext keys, 120s).

Compliance: P11, P12, P19, P23
"""

from __future__ import annotations

import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable

TTL_SEC = 120.0


@dataclass
class _Entry:
    provider: str
    key_plain: str
    key_length: int
    source: str
    exp_mono: float


def _new_detection_id() -> str:
    return secrets.token_hex(16)


class DetectionStore:
    def __init__(
        self,
        *,
        time_fn: Callable[[], float] = time.monotonic,
        on_expire: Callable[[str, int], None] | None = None,
    ) -> None:
        self._lock = threading.Lock()
        self._data: dict[str, _Entry] = {}
        self._time_fn = time_fn
        self._on_expire = on_expire

    def _sweep(self) -> int:
        now = self._time_fn()
        dead: list[str] = []
        for did, e in self._data.items():
            if e.exp_mono <= now:
                dead.append(did)
        n = 0
        for did in dead:
            self._data.pop(did, None)
            n += 1
        if n and self._on_expire:
            self._on_expire("vault.scan.expired", n)
        return n

    def add_detection(
        self,
        provider: str,
        key_plain: str,
        key_length: int,
        source: str,
    ) -> str:
        with self._lock:
            self._sweep()
            did = _new_detection_id()
            self._data[did] = _Entry(
                provider=provider,
                key_plain=key_plain,
                key_length=key_length,
                source=source,
                exp_mono=self._time_fn() + TTL_SEC,
            )
        return did

    def pop_detection(self, detection_id: str) -> dict[str, Any] | None:
        with self._lock:
            self._sweep()
            ent = self._data.pop(detection_id, None)
            if not ent:
                return None
            if self._time_fn() > ent.exp_mono:
                return None
            return {
                "provider": ent.provider,
                "key": ent.key_plain,
            }


def _default_on_expire(event: str, n: int) -> None:
    if event == "vault.scan.expired" and n > 0:
        from . import receipts

        receipts.write_scan_expired_receipt(detection_count=n)


_store: DetectionStore | None = None


def get_detection_store() -> DetectionStore:
    global _store
    if _store is None:
        _store = DetectionStore(on_expire=_default_on_expire)
    return _store


def set_detection_store_for_tests(st: DetectionStore | None) -> None:
    global _store
    _store = st
