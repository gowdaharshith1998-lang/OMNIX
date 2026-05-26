"""Encoding-anomaly prober.

For VARCHAR / TEXT columns, sample up to 1000 distinct values and look for:
  * non-UTF-8 byte sequences (residue from EBCDIC migrations, severity=blocker)
  * mojibake patterns (e.g. ``Ã©`` instead of ``é``, severity=warn)
  * unexpected control characters or replacement glyphs (severity=warn)
"""

from __future__ import annotations

import re
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

_SAMPLE_LIMIT = 1000
_MOJIBAKE_RE = re.compile(
    r"Ã[©¨ª«¬®¯°±²³´µ¶·¸¹º»¼½¾¿]|"
    r"Â[\xa0-\xbf]|"
    r"Ã|"  # double-encoded
    r"�"          # replacement char
)
_CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _classify(values):
    mojibake = []
    nonutf8_proxy = []
    control = []
    for v in values:
        if v is None:
            continue
        s = str(v)
        if _MOJIBAKE_RE.search(s):
            mojibake.append(s)
        if _CONTROL_RE.search(s):
            control.append(s)
        # rough non-UTF-8 proxy: presence of � Unicode replacement
        if "�" in s and s not in mojibake:
            nonutf8_proxy.append(s)
    return mojibake, nonutf8_proxy, control


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
    if dialect == "postgres":
        sql = f"SELECT DISTINCT {col_q} FROM {table_q} LIMIT {_SAMPLE_LIMIT}"
    elif dialect == "mysql":
        sql = f"SELECT DISTINCT {col_q} FROM {table_q} LIMIT {_SAMPLE_LIMIT}"
    elif dialect == "oracle":
        sql = f"SELECT DISTINCT {col_q} FROM {table_q} FETCH FIRST {_SAMPLE_LIMIT} ROWS ONLY"
    else:
        return package_error(request, "error", f"unsupported dialect: {dialect}", 0)

    def _query():
        cur = conn.cursor()
        cur.execute(sql)
        rows = cur.fetchall() or []
        return [r[0] if isinstance(r, (tuple, list)) else r for r in rows]

    values, elapsed, status = with_timeout(_query, timeout_ms)
    if status == "timeout":
        return package_error(request, "timeout", "query exceeded timeout", elapsed)
    if status is not None:
        return package_error(request, "error", status, elapsed)

    mojibake, nonutf8, control = _classify(values)
    findings = []
    if nonutf8:
        findings.append(
            AnomalyFinding(
                probe_category="encoding_anomaly",
                legacy_table=request.legacy_table,
                legacy_column=request.legacy_column,
                anomaly_type="non_utf8_bytes",
                severity="blocker",
                sample_values=tuple(str(s) for s in nonutf8[:5]),
                affected_row_count=len(nonutf8),
                remediation_hint=(
                    "Non-UTF-8 byte sequences detected. "
                    "D3 transformer must (a) re-decode from source encoding (e.g. EBCDIC, latin1) "
                    "and re-encode UTF-8, or (b) quarantine the rows for operator review."
                ),
                requires_human_decision=True,
            )
        )
    if mojibake:
        findings.append(
            AnomalyFinding(
                probe_category="encoding_anomaly",
                legacy_table=request.legacy_table,
                legacy_column=request.legacy_column,
                anomaly_type="mojibake",
                severity="warn",
                sample_values=tuple(str(s) for s in mojibake[:5]),
                affected_row_count=len(mojibake),
                remediation_hint=(
                    "Double-encoded text (mojibake) detected. "
                    "D3 transformer should attempt latin1->utf8 round-trip correction."
                ),
                requires_human_decision=False,
            )
        )
    if control:
        findings.append(
            AnomalyFinding(
                probe_category="encoding_anomaly",
                legacy_table=request.legacy_table,
                legacy_column=request.legacy_column,
                anomaly_type="embedded_control_chars",
                severity="warn",
                sample_values=tuple(repr(s)[:80] for s in control[:5]),
                affected_row_count=len(control),
                remediation_hint=(
                    "Embedded control characters detected. "
                    "D3 transformer should strip or escape them."
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
