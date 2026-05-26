"""Sentinel-value prober.

Detects common "magic" placeholder values:
  * Dates: 1900-01-01, 1970-01-01, 9999-12-31
  * Integers: -1, 99999, 999999
  * Strings: 'N/A', 'NULL', 'UNKNOWN', '', '-'
"""

from __future__ import annotations

from typing import Optional

from omnix.dm._types import (
    AnomalyFinding,
    ColumnSpec,
    Dialect,
    ProbeRequest,
    ProbeResult,
)
from omnix.dm.d2_edge_case_profiling.probers._base import (
    DEFAULT_TIMEOUT_MS,
    DBConnection,
    package_error,
    quote_ident,
    with_timeout,
)

# Note: sentinel values are not user-supplied — they come from the in-process
# whitelist below — so substituting them into a SQL IN clause is safe. We still
# build the literals via repr() and reject any value containing a single quote.

_DATE_SENTINELS = ("1900-01-01", "1970-01-01", "9999-12-31")
_INT_SENTINELS = (-1, 99999, 999999)
_STRING_SENTINELS = ("N/A", "NULL", "UNKNOWN", "", "-")
_SENTINEL_RATE_FLOOR = 0.01  # 1%


def _safe_literal(s) -> str:
    if isinstance(s, int):
        return str(s)
    if isinstance(s, str):
        if "'" in s or "\x00" in s or "\n" in s or "\r" in s:
            raise ValueError(f"unsafe sentinel literal: {s!r}")
        return "'" + s + "'"
    raise TypeError(f"unsupported sentinel literal type: {type(s).__name__}")


def run(
    request: ProbeRequest,
    conn: DBConnection,
    *,
    dialect: Dialect = "postgres",
    column_spec: Optional[ColumnSpec] = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> ProbeResult:
    if column_spec is None:
        return package_error(
            request, "error", "sentinel_value requires column_spec", 0
        )

    norm = column_spec.normalized_type
    if norm in {"STRING"}:
        sentinels = _STRING_SENTINELS
    elif norm in {"DATE", "TIMESTAMP", "TIMESTAMP_TZ"}:
        sentinels = _DATE_SENTINELS
    elif norm in {"INTEGER", "DECIMAL", "FLOAT"}:
        sentinels = _INT_SENTINELS  # type: ignore[assignment]
    else:
        return ProbeResult(
            request=request,
            findings=(),
            status="ok",
            duration_ms=0,
            reason=f"sentinel detection N/A for normalized_type={norm}",
        )

    table_q = quote_ident(request.legacy_table, dialect)
    col_q = quote_ident(request.legacy_column, dialect)
    literals = ",".join(_safe_literal(s) for s in sentinels)

    sql = f"SELECT COUNT(*) FROM {table_q} WHERE {col_q} IN ({literals})"
    sql_total = f"SELECT COUNT(*) FROM {table_q} WHERE {col_q} IS NOT NULL"

    def _query():
        cur = conn.cursor()
        cur.execute(sql)
        hit = cur.fetchone()
        cur.execute(sql_total)
        tot = cur.fetchone()
        hit_v = int(hit[0]) if isinstance(hit, (tuple, list)) else int(hit)
        tot_v = int(tot[0]) if isinstance(tot, (tuple, list)) else int(tot)
        return hit_v, tot_v

    result, elapsed, status = with_timeout(_query, timeout_ms)
    if status == "timeout":
        return package_error(request, "timeout", "query exceeded timeout", elapsed)
    if status is not None:
        return package_error(request, "error", status, elapsed)
    hit, tot = result

    findings = []
    if tot > 0 and hit > 0:
        rate = hit / tot
        if rate >= _SENTINEL_RATE_FLOOR:
            findings.append(
                AnomalyFinding(
                    probe_category="sentinel_value",
                    legacy_table=request.legacy_table,
                    legacy_column=request.legacy_column,
                    anomaly_type=f"{norm.lower()}_sentinel_present",
                    severity="warn",
                    sample_values=tuple(str(s) for s in sentinels),
                    affected_row_count=hit,
                    remediation_hint=(
                        f"{rate:.1%} of non-null values match a known sentinel "
                        f"({list(sentinels)}). D3 must decide whether to translate to NULL, "
                        "preserve verbatim, or quarantine."
                    ),
                    requires_human_decision=False,
                )
            )

    return ProbeResult(
        request=request,
        findings=tuple(findings),
        status="ok",
        duration_ms=elapsed,
        reason=None,
    )


__all__ = ["run"]
