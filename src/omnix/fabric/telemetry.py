"""src/fabric/telemetry.py — in-memory circular buffer (last 1000)
Compliance: P11, P19, D6
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

_MAX = 1000
_buf: deque[dict[str, Any]] = deque(maxlen=_MAX)
_lock = threading.Lock()


def reset_for_tests() -> None:
    with _lock:
        _buf.clear()


def record(entry: dict[str, Any]) -> None:
    with _lock:
        _buf.append(entry)


def recent(limit: int | None = None) -> list[dict[str, Any]]:
    with _lock:
        items = list(_buf)
    if limit is not None:
        return items[-limit:]
    return items


def today_totals() -> dict[str, Any]:
    with _lock:
        items = list(_buf)
    calls = len(items)
    successes = sum(1 for e in items if e.get("status") == "ok")
    failures = sum(1 for e in items if e.get("status") != "ok")
    cost = round(sum(float(e.get("cost_usd", 0) or 0) for e in items), 6)
    return {
        "calls": calls,
        "successes": successes,
        "failures": failures,
        "total_cost_usd": cost,
    }
