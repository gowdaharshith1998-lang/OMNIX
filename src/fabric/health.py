"""src/fabric/health.py — provider last-success timestamps for routing
Compliance: P12, P20
"""

from __future__ import annotations

import threading
import time
from typing import Callable

_lock = threading.Lock()
_last_ok: dict[str, float] = {}
_time_fn: Callable[[], float] = time.time


def set_time_fn_for_tests(fn: Callable[[], float] | None) -> None:
    global _time_fn
    _time_fn = fn or time.time


def reset_for_tests() -> None:
    with _lock:
        _last_ok.clear()


def mark_ok(provider: str) -> None:
    with _lock:
        _last_ok[provider] = _time_fn()


def is_available(provider: str, window_s: float = 60.0) -> bool:
    with _lock:
        ts = _last_ok.get(provider)
    if ts is None:
        return True
    return (_time_fn() - ts) < window_s


def last_ok_timestamp(provider: str) -> float | None:
    with _lock:
        t = _last_ok.get(provider)
        return float(t) if t is not None else None
