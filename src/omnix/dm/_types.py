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


# ---------- D4 Bulk Import types (PR C append-only) ----------


@dataclass(frozen=True)
class Row:
    legacy_table: str
    pk_value_repr: str
    column_values: Tuple[Tuple[str, object], ...]


@dataclass(frozen=True)
class Batch:
    migration_id: str
    table: str
    batch_no: int
    batch_id: str
    rows: Tuple[Row, ...]
    snapshot_lsn: Optional[str] = None


@dataclass(frozen=True)
class TransformedRow:
    legacy_pk_value_repr: str
    target_column_values: Tuple[Tuple[str, object], ...]


@dataclass(frozen=True)
class TransformedBatch:
    migration_id: str
    table: str
    batch_no: int
    batch_id: str
    transformed_rows: Tuple[TransformedRow, ...]
    quarantined_offsets: Tuple[int, ...] = ()


RowFailureCategory = Literal[
    "transform_error",
    "transform_timeout",
    "transform_oom",
    "target_constraint_violation",
    "target_connection_error",
    "schema_mismatch",
    "unmapped_column",
    "security_violation",
]


@dataclass(frozen=True)
class RowQuarantineEntry:
    migration_id: str
    batch_id: str
    row_offset: int
    legacy_table: str
    legacy_pk_value_hash: str
    failure_category: str  # one of RowFailureCategory
    failure_detail: str
    transformer_spec_hash: Optional[str]
    retry_count: int
    timestamp: str
    raw_values_json: Optional[str] = None  # only when OMNIX_DM_QUARANTINE_INCLUDE_VALUES=1


@dataclass(frozen=True)
class BatchReceipt:
    migration_id: str
    table: str
    batch_no: int
    batch_id: str
    predecessor_hash: str
    rows_read: int
    rows_written: int
    rows_quarantined: int
    quarantine_offsets: Tuple[int, ...]
    transformer_spec_hashes: Tuple[str, ...]
    target_db_fingerprint: str
    timestamp_start: str
    timestamp_end: str
    elapsed_seconds: float


BulkPhase = Literal["planning", "snapshot", "running", "complete", "halted"]


@dataclass(frozen=True)
class BulkResult:
    migration_id: str
    phase: str  # BulkPhase
    tables_complete: Tuple[str, ...]
    tables_halted: Tuple[str, ...]
    unmapped_columns: Tuple[str, ...]
    total_rows_written: int
    total_rows_quarantined: int
    partial: bool
    snapshot_lsn: Optional[str]


# ---------- D5 Change Data Capture types (PR C append-only) ----------

ChangeOp = Literal["I", "U", "D", "T"]


@dataclass(frozen=True)
class RelationSchema:
    relation_id: int
    schema_name: str
    table_name: str
    columns: Tuple[Tuple[str, int, bool], ...]  # (name, type_oid, part_of_pkey)
    replica_identity: Literal["default", "nothing", "full", "index"]


@dataclass(frozen=True)
class ChangeEvent:
    op: str  # ChangeOp
    relation_id: int
    schema_name: str
    table_name: str
    lsn: str
    xid: int
    commit_timestamp: Optional[str]
    before: Optional[Tuple[Tuple[str, object], ...]]
    after: Optional[Tuple[Tuple[str, object], ...]]
    # pgoutput stamps every change in a transaction with the same commit
    # LSN, so (lsn, seq) — not lsn alone — is the unique identity of a
    # change for idempotency purposes.
    seq: int = 0
    # Replica-identity key column names from the relation message; empty
    # when the relation declared no usable key.
    key_columns: Tuple[str, ...] = ()


@dataclass(frozen=True)
class CDCEventReceipt:
    migration_id: str
    event_lsn: str
    relation_id: int
    table: str
    op: str
    predecessor_hash: str
    transformer_spec_hashes: Tuple[str, ...]
    applied_at_target_timestamp: str
    legacy_to_target_lag_ms: int


CDCFailureCategory = Literal[
    "transform_error",
    "transform_timeout",
    "transform_oom",
    "target_constraint_violation",
    "target_connection_error",
    "unmapped_column",
    "unknown_relation",
    "schema_drift",
]


@dataclass(frozen=True)
class CDCEventQuarantineEntry:
    migration_id: str
    event_lsn: str
    relation_id: int
    table: str
    op: str
    failure_category: str  # one of CDCFailureCategory
    failure_detail: str
    timestamp: str


@dataclass(frozen=True)
class LagReport:
    migration_id: str
    timestamp: str
    legacy_current_lsn: Optional[str]
    target_applied_lsn: Optional[str]
    legacy_unreachable: bool
    target_unreachable: bool
    lag_lsn_bytes: Optional[int]
    lag_estimated_seconds: Optional[float]
    events_replayed_last_interval: int
    events_quarantined_last_interval: int
    unhandled_event_types_seen: Tuple[str, ...] = ()


@dataclass(frozen=True)
class ParityMetric:
    table: str
    rows_compared: int
    rows_diverged: int
    divergence_rate: float


@dataclass(frozen=True)
class CutoverProposal:
    migration_id: str
    timestamp: str
    predecessor_hash: str
    sustained_window_seconds: int
    measured_lag_seconds: float
    parity_threshold: float
    parity_metrics: Tuple[ParityMetric, ...]
    parity_not_met: bool
    recommended_action: Literal["operator_sign", "wait_longer", "investigate_divergence"]
    operator_signoff: Optional[dict] = None


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
    # D4 (PR C)
    "Row",
    "Batch",
    "TransformedRow",
    "TransformedBatch",
    "RowFailureCategory",
    "RowQuarantineEntry",
    "BatchReceipt",
    "BulkPhase",
    "BulkResult",
    # D5 (PR C)
    "ChangeOp",
    "RelationSchema",
    "ChangeEvent",
    "CDCEventReceipt",
    "CDCFailureCategory",
    "CDCEventQuarantineEntry",
    "LagReport",
    "ParityMetric",
    "CutoverProposal",
]
