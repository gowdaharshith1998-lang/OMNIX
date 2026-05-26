"""Precision-boundary prober.

For NUMERIC / NUMBER / DECIMAL columns: sample MAX(ABS()) / MIN(ABS()) and
compare against the target type's precision. Surfaces blockers when actual
range exceeds the target type's precision.
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
    target_precision: Optional[int] = None,
    target_scale: Optional[int] = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> ProbeResult:
    if column_spec is None or column_spec.normalized_type not in {"DECIMAL", "INTEGER", "FLOAT"}:
        # Not a numeric column — nothing to probe.
        return ProbeResult(
            request=request,
            findings=(),
            status="ok",
            duration_ms=0,
            reason="non-numeric column, skipped",
        )

    table_q = quote_ident(request.legacy_table, dialect)
    col_q = quote_ident(request.legacy_column, dialect)
    sql = f"SELECT MAX(ABS({col_q})), MIN(ABS({col_q})) FROM {table_q} WHERE {col_q} IS NOT NULL"

    def _query():
        cur = conn.cursor()
        cur.execute(sql)
        row = cur.fetchone() or (None, None)
        return row

    result, elapsed, status = with_timeout(_query, timeout_ms)
    if status == "timeout":
        return package_error(request, "timeout", "query exceeded timeout", elapsed)
    if status is not None:
        return package_error(request, "error", status, elapsed)

    max_v, min_v = result
    findings = []
    if max_v is None:
        return ProbeResult(
            request=request,
            findings=(),
            status="ok",
            duration_ms=elapsed,
            reason="empty or all-null column",
        )

    try:
        max_v_f = float(max_v)
    except (TypeError, ValueError):
        return package_error(
            request, "error", f"could not coerce MAX(ABS) to float: {max_v!r}", elapsed
        )

    if target_precision is not None:
        max_target = 10 ** target_precision - 1
        if max_v_f > max_target:
            findings.append(
                AnomalyFinding(
                    probe_category="precision_boundary",
                    legacy_table=request.legacy_table,
                    legacy_column=request.legacy_column,
                    anomaly_type="value_exceeds_target_precision",
                    severity="blocker",
                    sample_values=(str(max_v),),
                    affected_row_count=None,
                    remediation_hint=(
                        f"Source MAX(ABS)={max_v} exceeds target precision {target_precision}. "
                        "D3 transformer must (a) widen the target type, "
                        "(b) round/truncate, or (c) reject out-of-range — operator must choose."
                    ),
                    requires_human_decision=True,
                )
            )

    src_scale = column_spec.dialect_specific.get("scale")
    if (
        target_scale is not None
        and isinstance(src_scale, int)
        and src_scale > target_scale
    ):
        findings.append(
            AnomalyFinding(
                probe_category="precision_boundary",
                legacy_table=request.legacy_table,
                legacy_column=request.legacy_column,
                anomaly_type="scale_truncation",
                severity="warn",
                sample_values=(),
                affected_row_count=None,
                remediation_hint=(
                    f"Source scale {src_scale} exceeds target scale {target_scale}. "
                    "D3 transformer must decide between rounding or banker's-rounding strategy."
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
