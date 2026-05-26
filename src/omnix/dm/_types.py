"""Shared dataclasses + Literal aliases for OMNIX-DM PR A.

Every type here is frozen — receipts are append-only and signed; mutating a
record after the fact would invalidate every downstream Merkle hash.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Optional, Tuple

Dialect = Literal["postgres", "mysql", "oracle", "mongodb"]

ProbeCategory = Literal[
    "null_distribution",
    "encoding_anomaly",
    "orphan_fk",
    "timezone_drift",
    "precision_boundary",
    "sentinel_value",
]

AnomalySeverity = Literal["info", "warn", "blocker"]

MappingStatus = Literal["ok", "low_confidence", "ambiguous", "no_match"]


# ---------- D1 inputs (parsed DDL) ----------


@dataclass(frozen=True)
class ColumnSpec:
    name: str
    raw_type: str
    normalized_type: str
    nullable: bool
    default: Optional[str]
    primary_key: bool
    unique: bool
    comment: Optional[str]
    dialect_specific: dict = field(default_factory=dict)


@dataclass(frozen=True)
class ForeignKeySpec:
    name: str
    from_table: str
    from_columns: Tuple[str, ...]
    to_table: str
    to_columns: Tuple[str, ...]
    on_delete: Optional[str] = None
    on_update: Optional[str] = None


@dataclass(frozen=True)
class IndexSpec:
    name: str
    table: str
    columns: Tuple[str, ...]
    unique: bool = False
    method: Optional[str] = None


@dataclass(frozen=True)
class TableSpec:
    name: str
    columns: Tuple[ColumnSpec, ...]
    primary_key: Tuple[str, ...] = ()
    foreign_keys: Tuple[ForeignKeySpec, ...] = ()
    indexes: Tuple[IndexSpec, ...] = ()
    comment: Optional[str] = None


@dataclass(frozen=True)
class SchemaSpec:
    dialect: Dialect
    name: str
    tables: Tuple[TableSpec, ...]
    parse_warnings: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ParseFailure:
    dialect: Dialect
    reason: str
    location: Optional[str] = None


# ---------- D1 enrichment (ColumnContext) ----------


@dataclass(frozen=True)
class CodebasePathUsage:
    file_path: str
    function_name: str
    line_number: int
    op_type: Literal["READ", "WRITE", "READ_WRITE"]


@dataclass(frozen=True)
class ColumnContext:
    column: ColumnSpec
    table_name: str
    sample_values: Tuple[str, ...] = ()
    sample_count: int = 0
    codebase_usage: Tuple[CodebasePathUsage, ...] = ()
    confidence_notes: Tuple[str, ...] = ()


# ---------- D1 output ----------


@dataclass(frozen=True)
class ColumnMapping:
    legacy_table: str
    legacy_column: str
    target_table: Optional[str]
    target_column: Optional[str]
    confidence: float
    status: MappingStatus
    candidates: Tuple[Tuple[str, str, float], ...] = ()
    rationale: str = ""


# ---------- D2 probe types ----------


@dataclass(frozen=True)
class ProbeRequest:
    category: ProbeCategory
    legacy_table: str
    legacy_column: str
    priority: float
    estimated_cost_ms: int
    rationale: str


@dataclass(frozen=True)
class ProbePlan:
    requests: Tuple[ProbeRequest, ...]
    total_estimated_cost_ms: int
    planner_iterations: int
    efe_trace: Tuple[float, ...]
    excluded: Tuple[Tuple[str, str, str], ...] = ()  # (table, col, reason)


@dataclass(frozen=True)
class AnomalyFinding:
    probe_category: ProbeCategory
    legacy_table: str
    legacy_column: str
    anomaly_type: str
    severity: AnomalySeverity
    sample_values: Tuple[str, ...]
    affected_row_count: Optional[int]
    remediation_hint: str
    requires_human_decision: bool


@dataclass(frozen=True)
class ProbeResult:
    request: ProbeRequest
    findings: Tuple[AnomalyFinding, ...]
    status: Literal["ok", "timeout", "error"]
    duration_ms: int
    reason: Optional[str] = None


__all__ = [
    "Dialect",
    "ProbeCategory",
    "AnomalySeverity",
    "MappingStatus",
    "ColumnSpec",
    "ForeignKeySpec",
    "IndexSpec",
    "TableSpec",
    "SchemaSpec",
    "ParseFailure",
    "CodebasePathUsage",
    "ColumnContext",
    "ColumnMapping",
    "ProbeRequest",
    "ProbePlan",
    "AnomalyFinding",
    "ProbeResult",
]
