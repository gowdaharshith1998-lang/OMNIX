"""Shared infrastructure for the 6 edge-case probers.

Every prober conforms to the ``Prober`` Protocol:

    def run(request: ProbeRequest, conn: DBConnection,
            *, column_spec: Optional[ColumnSpec] = None,
            timeout_ms: int = 10_000) -> ProbeResult

Probers MUST:
  * Use parameterized SQL only — never f-string user data into a statement.
  * Honor the ``timeout_ms`` budget and emit ``status='timeout'`` cleanly.
  * Surface SQL errors as ``status='error'`` with the reason — never swallow.
  * Provide a non-empty ``remediation_hint`` on every AnomalyFinding.
"""

from __future__ import annotations

import time
from typing import Any, Callable, Optional, Protocol

from omnix.dm._types import (
    AnomalyFinding,
    ColumnSpec,
    Dialect,
    ProbeRequest,
    ProbeResult,
)

DEFAULT_TIMEOUT_MS = 10_000


class DBConnection(Protocol):
    """Minimal DB-API 2.0 surface required by every prober."""

    def cursor(self) -> Any: ...


def quote_ident(name: str, dialect: Dialect = "postgres") -> str:
    if dialect == "mysql":
        if "`" in name:
            raise ValueError(f"refusing to quote identifier containing backtick: {name!r}")
        return f"`{name}`"
    if '"' in name:
        raise ValueError(f"refusing to quote identifier containing dquote: {name!r}")
    return f'"{name}"'


def with_timeout(
    fn: Callable[[], Any], timeout_ms: int
) -> tuple[Any, int, Optional[str]]:
    """Run ``fn`` with a wall-clock timeout. Returns ``(result_or_None,
    elapsed_ms, status)`` where ``status`` is ``None`` on success, ``"timeout"``
    if the function exceeded the budget, or an error message string on
    exception.

    NOTE: this implements a wall-clock check around the callable; it does
    *not* preemptively kill the work. For DB queries, the conn-level
    statement_timeout must also be set by the caller — see ``set_statement_timeout``.
    """
    start = time.monotonic()
    try:
        result = fn()
    except Exception as e:  # noqa: BLE001 — explicit surfacing
        elapsed = int((time.monotonic() - start) * 1000)
        return None, elapsed, f"{type(e).__name__}: {e}"
    elapsed = int((time.monotonic() - start) * 1000)
    if elapsed > timeout_ms:
        return result, elapsed, "timeout"
    return result, elapsed, None


def set_statement_timeout(conn: DBConnection, timeout_ms: int, dialect: Dialect) -> None:
    """Apply a per-statement timeout server-side. No-op if dialect unsupported."""
    try:
        cur = conn.cursor()
        if dialect == "postgres":
            cur.execute(f"SET LOCAL statement_timeout = {int(timeout_ms)}")
        elif dialect == "mysql":
            cur.execute(f"SET SESSION MAX_EXECUTION_TIME = {int(timeout_ms)}")
        # Oracle uses RESOURCE_LIMIT / profile-level — not set here.
    except Exception:
        pass


def package_error(
    request: ProbeRequest, status: str, reason: str, duration_ms: int
) -> ProbeResult:
    return ProbeResult(
        request=request,
        findings=(),
        status=status,  # type: ignore[arg-type]
        duration_ms=duration_ms,
        reason=reason,
    )


__all__ = [
    "DEFAULT_TIMEOUT_MS",
    "DBConnection",
    "quote_ident",
    "with_timeout",
    "set_statement_timeout",
    "package_error",
]
