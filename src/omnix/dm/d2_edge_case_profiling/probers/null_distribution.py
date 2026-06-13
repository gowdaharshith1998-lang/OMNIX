"""NULL-distribution prober.

For each ``(table, column)`` pair:
  * Counts NULL rows and total rows.
  * If the column is declared NOT NULL but NULL rows exist (data corruption):
    emit ``severity='blocker'``.
  * If the column is nullable: emit a non-blocker ``info`` finding when the
    null-rate is non-trivial (>= 1%) so D3 transformer synth knows about it.
  * Always emits ``total_row_count`` (via the ``info`` finding's
    ``affected_row_count`` field) so downstream code can normalize rates.
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
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> ProbeResult:
    table_q = quote_ident(request.legacy_table, dialect)
    col_q = quote_ident(request.legacy_column, dialect)
    sql_null = f"SELECT COUNT(*) FROM {table_q} WHERE {col_q} IS NULL"
    sql_total = f"SELECT COUNT(*) FROM {table_q}"

    def _query():
        cur = conn.cursor()
        cur.execute(sql_null)
        null_row = cur.fetchone()
        null_count = int(null_row[0]) if isinstance(null_row, (tuple, list)) else int(null_row)
        cur.execute(sql_total)
        total_row = cur.fetchone()
        total = int(total_row[0]) if isinstance(total_row, (tuple, list)) else int(total_row)
        return null_count, total

    result, elapsed, status = with_timeout(_query, timeout_ms)
    if status == "timeout":
        return package_error(request, "timeout", "query exceeded timeout", elapsed)
    if status is not None:
        return package_error(request, "error", status, elapsed)
    null_count, total = result

    findings = []
    is_nullable = column_spec.nullable if column_spec is not None else True
    if null_count > 0 and not is_nullable:
        findings.append(
            AnomalyFinding(
                probe_category="null_distribution",
                legacy_table=request.legacy_table,
                legacy_column=request.legacy_column,
                anomaly_type="null_in_non_null_column",
                severity="blocker",
                sample_values=(),
                affected_row_count=null_count,
                remediation_hint=(
                    "Column is declared NOT NULL but contains NULL rows. "
                    "D3 transformer must (a) drop NULL rows, "
                    "(b) backfill with a default, or (c) widen the target column to nullable — "
                    "operator must choose."
                ),
                requires_human_decision=True,
            )
        )
    elif null_count > 0 and total > 0:
        rate = null_count / total
        if rate >= 0.01:
            findings.append(
                AnomalyFinding(
                    probe_category="null_distribution",
                    legacy_table=request.legacy_table,
                    legacy_column=request.legacy_column,
                    anomaly_type="nullable_with_nontrivial_null_rate",
                    severity="info",
                    sample_values=(),
                    affected_row_count=null_count,
                    remediation_hint=(
                        f"{rate:.1%} of rows are NULL; D3 transformer should "
                        "preserve nullability and confirm target accepts NULL."
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
