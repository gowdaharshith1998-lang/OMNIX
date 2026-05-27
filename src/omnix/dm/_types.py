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


# ---------- D3 transformer-synthesis types (PR B append-only) ----------

TransformerTier = Literal["python", "sql", "datalog"]


@dataclass(frozen=True)
class PropertyDef:
    name: str
    hypothesis_strategy: str
    assertion: str
    derives_from_blocker: Optional[str]
    rationale: str


@dataclass(frozen=True)
class PropertySet:
    column_mapping_key: str
    properties: Tuple[PropertyDef, ...]
    coverage_complete: bool
    missing_coverage_reasons: Tuple[str, ...]


@dataclass(frozen=True)
class SketchHint:
    sketch_id: str
    type_pair: Tuple[str, str]
    template: str
    applicable_blockers: Tuple[str, ...]
    historical_pass_rate: float


@dataclass(frozen=True)
class SynthesizerResult:
    python_source: str
    properties_source: str
    raw_response: str
    prompt_tokens: int
    completion_tokens: int
    model_id: str


@dataclass(frozen=True)
class LLMParseFailure:
    reason: str
    raw_response_excerpt: str


@dataclass(frozen=True)
class APIFailure:
    reason: str
    error_type: str


@dataclass(frozen=True)
class SecurityViolation:
    node_type: str
    reason: str
    source_excerpt: str


@dataclass(frozen=True)
class ExecutionTimeout:
    input_value: str
    timeout_ms: int


@dataclass(frozen=True)
class ExecutionOOM:
    input_value: str
    rss_bytes: int


@dataclass(frozen=True)
class ExecutionError:
    input_value: str
    error_type: str
    error_message: str


@dataclass(frozen=True)
class MFI:
    """Minimum Failing Input — concrete failing example from Hypothesis shrinking."""

    property_name: str
    input_value_repr: str
    expected_output_repr: str
    actual_output_repr: str
    hint: str


@dataclass(frozen=True)
class TierFailure:
    tier: str  # one of TransformerTier
    reason: str
    failing_mfi: Optional[MFI] = None


@dataclass(frozen=True)
class TransformerSpec:
    column_mapping_key: str
    python_source: str
    sql_case: Optional[str]
    datalog_rule: Optional[str]
    properties_passed: Tuple[str, ...]
    properties_failed: Tuple[str, ...]  # MUST be empty for a Success spec
    mfi_history: Tuple[MFI, ...]
    iterations_used: int
    cegis_pruned_sketches: Tuple[str, ...]
    tier_failures: Tuple[TierFailure, ...]
    tier_chosen: str  # one of TransformerTier
    confidence: float
    requires_operator_review: bool
    bisimulation_placeholder: dict


@dataclass(frozen=True)
class ReflexionSuccess:
    transformer_spec: TransformerSpec
    iterations_used: int
    mfi_history: Tuple[MFI, ...]
    pruned_sketches: Tuple[str, ...]


@dataclass(frozen=True)
class ReflexionHalt:
    column_mapping_key: str
    halt_reason: Literal[
        "iteration_cap",
        "security_violation",
        "parse_failure",
        "all_sketches_pruned",
        "loop_walltime",
        "api_failure",
    ]
    latest_python_source: str
    failing_mfis: Tuple[MFI, ...]
    last_critique: str
    iterations_used: int
    security_violation: Optional[SecurityViolation] = None


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
    # D3 (PR B)
    "TransformerTier",
    "PropertyDef",
    "PropertySet",
    "SketchHint",
    "SynthesizerResult",
    "LLMParseFailure",
    "APIFailure",
    "SecurityViolation",
    "ExecutionTimeout",
    "ExecutionOOM",
    "ExecutionError",
    "MFI",
    "TierFailure",
    "TransformerSpec",
    "ReflexionSuccess",
    "ReflexionHalt",
]
