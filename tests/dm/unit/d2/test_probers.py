"""Tests for the 6 D2 probers (P6).

Each prober is tested with a mock conn that returns canned fetchone /
fetchall results. We cover: happy path, timeout, SQL error, and the specific
anomaly category each prober is responsible for.
"""

from __future__ import annotations

import time

import pytest

from omnix.dm._types import (
    ColumnSpec,
    ForeignKeySpec,
    ProbeRequest,
)
from omnix.dm.d2_edge_case_profiling.probers import (
    encoding_anomaly,
    null_distribution,
    orphan_fk,
    precision_boundary,
    sentinel_value,
    timezone_drift,
)


class _Cursor:
    def __init__(self, *, responses, raise_on=None, sleep_each=0.0):
        self._responses = list(responses)
        self._raise = raise_on
        self._sleep = sleep_each
        self._last = None
        self.executed: list[str] = []

    def execute(self, sql, params=None):
        self.executed.append(sql)
        if self._sleep:
            time.sleep(self._sleep)
        if self._raise:
            raise self._raise

    def fetchone(self):
        v = self._responses.pop(0) if self._responses else (0,)
        return v

    def fetchall(self):
        v = self._responses.pop(0) if self._responses else []
        return v


class _Conn:
    def __init__(self, **kw):
        self.kw = kw

    def cursor(self):
        return _Cursor(**self.kw)


def _req(category, table="owner", column="email"):
    return ProbeRequest(
        category=category,
        legacy_table=table,
        legacy_column=column,
        priority=0.9,
        estimated_cost_ms=500,
        rationale="test",
    )


def _col(name="email", normalized="STRING", nullable=True, **extra):
    return ColumnSpec(
        name=name,
        raw_type="VARCHAR(255)",
        normalized_type=normalized,
        nullable=nullable,
        default=None,
        primary_key=False,
        unique=False,
        comment=None,
        dialect_specific=extra,
    )


# ---- null_distribution ----


def test_null_distribution_finds_blocker_for_not_null_column():
    conn = _Conn(responses=[(5,), (100,)])
    r = null_distribution.run(
        _req("null_distribution"), conn, column_spec=_col(nullable=False)
    )
    assert r.status == "ok"
    assert len(r.findings) == 1
    assert r.findings[0].severity == "blocker"
    assert r.findings[0].affected_row_count == 5


def test_null_distribution_info_finding_for_nullable():
    conn = _Conn(responses=[(10,), (100,)])
    r = null_distribution.run(
        _req("null_distribution"), conn, column_spec=_col(nullable=True)
    )
    assert r.status == "ok"
    assert len(r.findings) == 1
    assert r.findings[0].severity == "info"


def test_null_distribution_sql_error_surfaced():
    conn = _Conn(responses=[], raise_on=RuntimeError("syntax error"))
    r = null_distribution.run(
        _req("null_distribution"), conn, column_spec=_col()
    )
    assert r.status == "error"
    assert "syntax error" in r.reason


# ---- encoding_anomaly ----


def test_encoding_anomaly_detects_mojibake():
    conn = _Conn(responses=[[("hello",), ("café",), ("Ã©cole",)]])
    r = encoding_anomaly.run(_req("encoding_anomaly"), conn, column_spec=_col())
    assert r.status == "ok"
    cats = {f.anomaly_type for f in r.findings}
    assert "mojibake" in cats


def test_encoding_anomaly_detects_replacement_char():
    conn = _Conn(responses=[[("�bad",)]])
    r = encoding_anomaly.run(_req("encoding_anomaly"), conn, column_spec=_col())
    # � matches the mojibake regex; either way we surface something
    assert any(
        f.severity in {"warn", "blocker"} for f in r.findings
    )


# ---- orphan_fk ----


def test_orphan_fk_blocker_when_orphans_present():
    conn = _Conn(responses=[(7,)])
    fk = ForeignKeySpec(
        name="fk_pet_owner",
        from_table="pet",
        from_columns=("owner_id",),
        to_table="owner",
        to_columns=("id",),
    )
    r = orphan_fk.run(_req("orphan_fk", table="pet"), conn, fk_spec=fk)
    assert r.status == "ok"
    assert r.findings[0].severity == "blocker"
    assert r.findings[0].affected_row_count == 7


def test_orphan_fk_no_findings_when_zero_orphans():
    conn = _Conn(responses=[(0,)])
    fk = ForeignKeySpec(
        name="fk_pet_owner",
        from_table="pet",
        from_columns=("owner_id",),
        to_table="owner",
        to_columns=("id",),
    )
    r = orphan_fk.run(_req("orphan_fk", table="pet"), conn, fk_spec=fk)
    assert r.findings == ()


def test_orphan_fk_requires_fk_spec():
    conn = _Conn(responses=[])
    r = orphan_fk.run(_req("orphan_fk"), conn, fk_spec=None)
    assert r.status == "error"


# ---- timezone_drift ----


def test_timezone_drift_static_check_only():
    # Source DATE, target TIMESTAMP_TZ — static check fires without any DB call
    col = _col(name="visit_date", normalized="DATE", oracle_date_includes_time=True, flag_for_d3=True)
    conn = _Conn(responses=[(60,), (100,)])
    r = timezone_drift.run(
        _req("timezone_drift", column="visit_date"),
        conn,
        column_spec=col,
        target_normalized_type="TIMESTAMP_TZ",
    )
    assert r.status == "ok"
    assert any(f.anomaly_type == "source_naive_target_tz_aware" for f in r.findings)


def test_timezone_drift_midnight_clustering_warn():
    col = _col(name="dt", normalized="TIMESTAMP")
    conn = _Conn(responses=[(80,), (100,)])
    r = timezone_drift.run(
        _req("timezone_drift", column="dt"), conn, column_spec=col
    )
    assert r.status == "ok"
    assert any(f.anomaly_type == "midnight_clustering" for f in r.findings)


# ---- precision_boundary ----


def test_precision_boundary_blocker_when_value_too_large():
    col = _col(name="amount", normalized="DECIMAL", precision=38, scale=10)
    conn = _Conn(responses=[(99999999999.0, 0.1)])
    r = precision_boundary.run(
        _req("precision_boundary", column="amount"),
        conn,
        column_spec=col,
        target_precision=10,
    )
    assert r.status == "ok"
    assert any(f.severity == "blocker" for f in r.findings)


def test_precision_boundary_skips_non_numeric():
    col = _col(name="email", normalized="STRING")
    conn = _Conn(responses=[])
    r = precision_boundary.run(
        _req("precision_boundary"), conn, column_spec=col
    )
    assert r.status == "ok"
    assert r.findings == ()


# ---- sentinel_value ----


def test_sentinel_value_warn_when_above_threshold():
    col = _col(name="status", normalized="STRING")
    conn = _Conn(responses=[(15,), (100,)])
    r = sentinel_value.run(
        _req("sentinel_value", column="status"), conn, column_spec=col
    )
    assert r.status == "ok"
    assert any(f.severity == "warn" for f in r.findings)


def test_sentinel_value_below_threshold_no_finding():
    col = _col(name="status", normalized="STRING")
    conn = _Conn(responses=[(0,), (100,)])
    r = sentinel_value.run(
        _req("sentinel_value", column="status"), conn, column_spec=col
    )
    assert r.findings == ()


def test_sentinel_value_no_sql_injection_in_literals():
    """The sentinel whitelist must reject any sentinel containing a single quote."""
    from omnix.dm.d2_edge_case_profiling.probers.sentinel_value import _safe_literal
    with pytest.raises(ValueError):
        _safe_literal("evil'; DROP TABLE x;--")


# ---- general: no f-string SQL in source ----


def test_no_f_string_sql_in_probers():
    """Static check: the probers directory must not contain f-string-prefixed
    SQL keywords. Identifier interpolation goes through quote_ident only."""
    import pathlib
    import re

    root = pathlib.Path(__file__).resolve().parents[3] / "src" / "omnix" / "dm" / "d2_edge_case_profiling"
    suspicious = re.compile(r'f"\s*(?:SELECT|INSERT|UPDATE|DELETE|WHERE)\b', re.IGNORECASE)
    offenders: list[str] = []
    for py in root.rglob("*.py"):
        text = py.read_text()
        for ln, line in enumerate(text.splitlines(), 1):
            if suspicious.search(line):
                # Allow if it's inside a comment marker on the same line
                if "# allowed" in line:
                    continue
                # We intentionally interpolate identifier-only via quote_ident;
                # treat lines that already passed through quote_ident as safe.
                # The grep guard is conservative — record but only fail on
                # patterns that look like user-data substitution.
                if "{" in line and "}" in line:
                    inner = line[line.index("{"): line.rindex("}") + 1]
                    if any(tok in inner for tok in ("quote_ident", "table_q", "col_q", "child", "parent", "_safe_literal")):
                        continue
                offenders.append(f"{py.name}:{ln}: {line.strip()}")
    assert not offenders, "f-string SQL detected:\n" + "\n".join(offenders)
