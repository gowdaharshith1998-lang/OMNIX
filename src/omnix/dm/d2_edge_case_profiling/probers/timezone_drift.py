"""Timezone-drift prober.

Detects TZ-strip / TZ-mismatch patterns when migrating from a TZ-naive source
type (Oracle DATE, MySQL DATETIME) to a TZ-aware target (PG TIMESTAMPTZ).
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


def run(
    request: ProbeRequest,
    conn: DBConnection,
    *,
    dialect: Dialect = "postgres",
    column_spec: Optional[ColumnSpec] = None,
    target_normalized_type: Optional[str] = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> ProbeResult:
    if column_spec is None:
        return package_error(
            request, "error", "timezone_drift requires column_spec", 0
        )

    source_norm = column_spec.normalized_type
    flag_d3 = column_spec.dialect_specific.get("flag_for_d3")
    findings = []
    elapsed = 0

    # Static analysis: if source is TIMESTAMP (no TZ) and target is TIMESTAMP_TZ,
    # a TZ-strip silently happened on insert.
    if (
        target_normalized_type == "TIMESTAMP_TZ"
        and source_norm in {"TIMESTAMP", "DATE", "DATETIME"}
    ):
        sev = "blocker" if flag_d3 else "warn"
        findings.append(
            AnomalyFinding(
                probe_category="timezone_drift",
                legacy_table=request.legacy_table,
                legacy_column=request.legacy_column,
                anomaly_type="source_naive_target_tz_aware",
                severity=sev,
                sample_values=(),
                affected_row_count=None,
                remediation_hint=(
                    "Source column has no time-zone information but target is TIMESTAMP WITH TIME ZONE. "
                    "D3 transformer must (a) assume a documented source TZ (e.g. UTC), "
                    "(b) backfill from an external TZ table, or (c) reject the migration — operator decision."
                ),
                requires_human_decision=True,
            )
        )

    # Cheap empirical check: do values cluster on midnight? Only run for
    # TIMESTAMP / DATE columns.
    if source_norm in {"TIMESTAMP", "DATE"} and dialect != "mongodb":
        table_q = quote_ident(request.legacy_table, dialect)
        col_q = quote_ident(request.legacy_column, dialect)
        if dialect == "postgres":
            sql = (
                f"SELECT COUNT(*) FROM {table_q} "
                f"WHERE {col_q} IS NOT NULL "
                f"AND EXTRACT(HOUR FROM {col_q}) = 0 "
                f"AND EXTRACT(MINUTE FROM {col_q}) = 0"
            )
            total_sql = f"SELECT COUNT(*) FROM {table_q} WHERE {col_q} IS NOT NULL"
        elif dialect == "mysql":
            sql = (
                f"SELECT COUNT(*) FROM {table_q} "
                f"WHERE {col_q} IS NOT NULL "
                f"AND HOUR({col_q}) = 0 AND MINUTE({col_q}) = 0"
            )
            total_sql = f"SELECT COUNT(*) FROM {table_q} WHERE {col_q} IS NOT NULL"
        else:  # oracle
            sql = (
                f"SELECT COUNT(*) FROM {table_q} "
                f"WHERE {col_q} IS NOT NULL "
                f"AND TO_CHAR({col_q}, 'HH24:MI:SS') = '00:00:00'"
            )
            total_sql = f"SELECT COUNT(*) FROM {table_q} WHERE {col_q} IS NOT NULL"

        def _query():
            cur = conn.cursor()
            cur.execute(sql)
            mid = cur.fetchone()
            cur.execute(total_sql)
            tot = cur.fetchone()
            mid_count = int(mid[0]) if isinstance(mid, (tuple, list)) else int(mid)
            tot_count = int(tot[0]) if isinstance(tot, (tuple, list)) else int(tot)
            return mid_count, tot_count

        result, elapsed, status = with_timeout(_query, timeout_ms)
        if status == "timeout":
            return package_error(request, "timeout", "query exceeded timeout", elapsed)
        if status is not None:
            return package_error(request, "error", status, elapsed)
        mid_count, tot_count = result
        if tot_count > 0 and (mid_count / tot_count) >= 0.5:
            findings.append(
                AnomalyFinding(
                    probe_category="timezone_drift",
                    legacy_table=request.legacy_table,
                    legacy_column=request.legacy_column,
                    anomaly_type="midnight_clustering",
                    severity="warn",
                    sample_values=(),
                    affected_row_count=mid_count,
                    remediation_hint=(
                        f"{mid_count}/{tot_count} non-null values fall exactly on midnight — "
                        "likely TZ-stripped or DATE-only inserted. D3 should treat as DATE, not TIMESTAMP."
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
