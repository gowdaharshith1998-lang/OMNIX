"""src/fabric/dedup.py — in-flight deduplication by idempotency_key
Compliance: P17, P19
"""

from __future__ import annotations

import threading
from concurrent.futures import Future
from typing import Any

_lock = threading.Lock()
_pending: dict[tuple[str, str], Future] = {}


def reset_for_tests() -> None:
    with _lock:
        _pending.clear()


def acquire(agent_id: str, idempotency_key: str) -> tuple[bool, Future]:
    """
    If duplicate, returns (True, existing_future).
    If leader, returns (False, new_future) registered for this key.
    """
    k = (agent_id, idempotency_key)
    with _lock:
        if k in _pending:
            return True, _pending[k]
        fut: Future = Future()
        _pending[k] = fut
        return False, fut


def complete(agent_id: str, idempotency_key: str, result: dict[str, Any]) -> None:
    k = (agent_id, idempotency_key)
    with _lock:
        fut = _pending.pop(k, None)
    if fut is not None and not fut.done():
        fut.set_result(result)
