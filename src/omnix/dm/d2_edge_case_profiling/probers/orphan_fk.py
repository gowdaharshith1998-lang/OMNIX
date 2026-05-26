"""Orphan-FK prober.

Detects rows whose FK column points at a parent that does not exist. Requires
a ``ForeignKeySpec`` parameter (caller supplies from the SchemaSpec) — the
``ProbeRequest`` alone doesn't carry FK metadata.
"""

from __future__ import annotations

from typing import Optional

from omnix.dm._types import (
    AnomalyFinding,
    Dialect,
    ForeignKeySpec,
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
    fk_spec: Optional[ForeignKeySpec] = None,
    timeout_ms: int = DEFAULT_TIMEOUT_MS,
) -> ProbeResult:
    if fk_spec is None:
        return package_error(
            request,
            "error",
            "orphan_fk requires fk_spec parameter (no FK metadata)",
            0,
        )

    child = quote_ident(fk_spec.from_table, dialect)
    parent = quote_ident(fk_spec.to_table, dialect)
    c_cols = [quote_ident(c, dialect) for c in fk_spec.from_columns]
    p_cols = [quote_ident(c, dialect) for c in fk_spec.to_columns]
    join_pred = " AND ".join(
        f"c.{cc} = p.{pc}" for cc, pc in zip(c_cols, p_cols)
    )
    parent_first_pk = p_cols[0]
    sql = (
        f"SELECT COUNT(*) FROM {child} c "
        f"LEFT JOIN {parent} p ON {join_pred} "
        f"WHERE p.{parent_first_pk} IS NULL AND c.{c_cols[0]} IS NOT NULL"
    )

    def _query():
        cur = conn.cursor()
        cur.execute(sql)
        row = cur.fetchone()
        return int(row[0]) if isinstance(row, (tuple, list)) else int(row)

    orphan_count, elapsed, status = with_timeout(_query, timeout_ms)
    if status == "timeout":
        return package_error(request, "timeout", "query exceeded timeout", elapsed)
    if status is not None:
        return package_error(request, "error", status, elapsed)

    findings = []
    if orphan_count > 0:
        findings.append(
            AnomalyFinding(
                probe_category="orphan_fk",
                legacy_table=fk_spec.from_table,
                legacy_column=fk_spec.from_columns[0],
                anomaly_type="orphan_foreign_key",
                severity="blocker",
                sample_values=(),
                affected_row_count=orphan_count,
                remediation_hint=(
                    "Foreign-key column references a non-existent parent row. "
                    "D3 transformer must either (a) delete orphan rows, "
                    "(b) create synthetic parents, or "
                    "(c) preserve as-is with FK deferred — operator must choose."
                ),
                requires_human_decision=True,
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
