"""JSON Schemas for OMNIX-DM signed manifests."""

from __future__ import annotations

COLUMN_MAPPING_MANIFEST_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "schema_version",
        "migration_id",
        "timestamp",
        "legacy_schema",
        "target_schema",
        "mappings",
        "predecessor_hash",
        "stats",
        "signing_algorithm",
        "public_key_fingerprint",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "omnix-dm/column-mapping/v1"},
        "migration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
        "timestamp": {"type": "string"},
        "legacy_schema": {"type": "object"},
        "target_schema": {"type": "object"},
        "mappings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "legacy_table",
                    "legacy_column",
                    "target_table",
                    "target_column",
                    "confidence",
                    "status",
                    "candidates",
                    "rationale",
                ],
                "properties": {
                    "legacy_table": {"type": "string"},
                    "legacy_column": {"type": "string"},
                    "target_table": {"type": ["string", "null"]},
                    "target_column": {"type": ["string", "null"]},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "status": {
                        "enum": ["ok", "low_confidence", "ambiguous", "no_match"]
                    },
                    "candidates": {"type": "array"},
                    "rationale": {"type": "string"},
                },
            },
        },
        "predecessor_hash": {"type": ["string", "null"]},
        "stats": {
            "type": "object",
            "required": [
                "total_legacy_columns",
                "status_ok_count",
                "status_low_confidence_count",
                "status_ambiguous_count",
                "status_no_match_count",
            ],
            "properties": {
                "total_legacy_columns": {"type": "integer", "minimum": 0},
                "status_ok_count": {"type": "integer", "minimum": 0},
                "status_low_confidence_count": {"type": "integer", "minimum": 0},
                "status_ambiguous_count": {"type": "integer", "minimum": 0},
                "status_no_match_count": {"type": "integer", "minimum": 0},
            },
        },
        "signing_algorithm": {"const": "ML-DSA-65"},
        "public_key_fingerprint": {"type": "string", "minLength": 8},
        "requires_operator_review": {"type": "boolean"},
    },
}


EDGE_CASE_MANIFEST_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "schema_version",
        "migration_id",
        "timestamp",
        "predecessor_hash",
        "findings",
        "probe_failures",
        "requires_operator_review",
        "stats",
        "signing_algorithm",
        "public_key_fingerprint",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "omnix-dm/edge-case-manifest/v1"},
        "migration_id": {"type": "string"},
        "timestamp": {"type": "string"},
        "predecessor_hash": {"type": "string", "minLength": 1},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "required": [
                    "probe_category",
                    "legacy_table",
                    "legacy_column",
                    "anomaly_type",
                    "severity",
                    "sample_values",
                    "affected_row_count",
                    "remediation_hint",
                    "requires_human_decision",
                ],
                "properties": {
                    "probe_category": {
                        "enum": [
                            "null_distribution",
                            "encoding_anomaly",
                            "orphan_fk",
                            "timezone_drift",
                            "precision_boundary",
                            "sentinel_value",
                        ]
                    },
                    "legacy_table": {"type": "string"},
                    "legacy_column": {"type": "string"},
                    "anomaly_type": {"type": "string"},
                    "severity": {"enum": ["info", "warn", "blocker"]},
                    "sample_values": {"type": "array", "items": {"type": "string"}},
                    "affected_row_count": {"type": ["integer", "null"]},
                    "remediation_hint": {"type": "string", "minLength": 1},
                    "requires_human_decision": {"type": "boolean"},
                },
            },
        },
        "probe_failures": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["probe_category", "legacy_table", "legacy_column", "status", "reason"],
                "properties": {
                    "probe_category": {"type": "string"},
                    "legacy_table": {"type": "string"},
                    "legacy_column": {"type": "string"},
                    "status": {"enum": ["timeout", "error"]},
                    "reason": {"type": "string"},
                },
            },
        },
        "requires_operator_review": {"type": "boolean"},
        "stats": {
            "type": "object",
            "required": [
                "total_probes_run",
                "total_findings",
                "blocker_count",
                "warn_count",
                "info_count",
                "timeout_count",
                "error_count",
            ],
            "properties": {
                "total_probes_run": {"type": "integer", "minimum": 0},
                "total_findings": {"type": "integer", "minimum": 0},
                "blocker_count": {"type": "integer", "minimum": 0},
                "warn_count": {"type": "integer", "minimum": 0},
                "info_count": {"type": "integer", "minimum": 0},
                "timeout_count": {"type": "integer", "minimum": 0},
                "error_count": {"type": "integer", "minimum": 0},
            },
        },
        "signing_algorithm": {"const": "ML-DSA-65"},
        "public_key_fingerprint": {"type": "string"},
    },
}


# ---------------------------------------------------------------------------
# D3 (PR B) schemas — APPEND-ONLY to keep PR A receipt verifiers untouched.
# ---------------------------------------------------------------------------


TRANSFORMER_SPEC_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "schema_version",
        "migration_id",
        "timestamp",
        "predecessor_hash",
        "column_mapping_key",
        "python_source",
        "sql_case",
        "datalog_rule",
        "properties_passed",
        "properties_failed",
        "mfi_history",
        "iterations_used",
        "cegis_pruned_sketches",
        "tier_failures",
        "tier_chosen",
        "confidence",
        "requires_operator_review",
        "bisimulation_placeholder",
        "signing_algorithm",
        "public_key_fingerprint",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "omnix-dm/transformer-spec/v1"},
        "migration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
        "timestamp": {"type": "string"},
        "predecessor_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "column_mapping_key": {"type": "string", "minLength": 1},
        "python_source": {"type": "string", "minLength": 1},
        "sql_case": {"type": ["string", "null"]},
        "datalog_rule": {"type": ["string", "null"]},
        "properties_passed": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
        },
        "properties_failed": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 0,
        },
        "mfi_history": {"type": "array"},
        "iterations_used": {"type": "integer", "minimum": 1, "maximum": 5},
        "cegis_pruned_sketches": {"type": "array", "items": {"type": "string"}},
        "tier_failures": {"type": "array"},
        "tier_chosen": {"enum": ["python", "sql", "datalog"]},
        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "requires_operator_review": {"type": "boolean"},
        "bisimulation_placeholder": {"type": "object"},
        "signing_algorithm": {"const": "ML-DSA-65"},
        "public_key_fingerprint": {"type": "string"},
    },
}


TRANSFORMER_HALT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "schema_version",
        "migration_id",
        "timestamp",
        "predecessor_hash",
        "column_mapping_key",
        "halt_reason",
        "latest_python_source",
        "failing_mfis",
        "last_critique",
        "iterations_used",
        "security_violation",
        "signing_algorithm",
        "public_key_fingerprint",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "omnix-dm/transformer-halt/v1"},
        "migration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
        "timestamp": {"type": "string"},
        "predecessor_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "column_mapping_key": {"type": "string", "minLength": 1},
        "halt_reason": {
            "enum": [
                "iteration_cap",
                "security_violation",
                "parse_failure",
                "all_sketches_pruned",
                "loop_walltime",
                "api_failure",
            ]
        },
        "latest_python_source": {"type": "string"},
        "failing_mfis": {"type": "array"},
        "last_critique": {"type": "string"},
        "iterations_used": {"type": "integer", "minimum": 0},
        "security_violation": {"type": ["object", "null"]},
        "signing_algorithm": {"const": "ML-DSA-65"},
        "public_key_fingerprint": {"type": "string"},
    },
}


# ---------------------------------------------------------------------------
# D4 + D5 (PR C) schemas — APPEND-ONLY.
# ---------------------------------------------------------------------------


BATCH_RECEIPT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "schema_version",
        "migration_id",
        "table",
        "batch_no",
        "batch_id",
        "predecessor_hash",
        "rows_read",
        "rows_written",
        "rows_quarantined",
        "quarantine_offsets",
        "transformer_spec_hashes",
        "target_db_fingerprint",
        "timestamp_start",
        "timestamp_end",
        "elapsed_seconds",
        "signing_algorithm",
        "public_key_fingerprint",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "omnix-dm/batch-receipt/v1"},
        "migration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
        "table": {"type": "string", "minLength": 1},
        "batch_no": {"type": "integer", "minimum": 0},
        "batch_id": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "predecessor_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "rows_read": {"type": "integer", "minimum": 0},
        "rows_written": {"type": "integer", "minimum": 0},
        "rows_quarantined": {"type": "integer", "minimum": 0},
        "quarantine_offsets": {"type": "array", "items": {"type": "integer", "minimum": 0}},
        "transformer_spec_hashes": {"type": "array", "items": {"type": "string"}},
        "target_db_fingerprint": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "timestamp_start": {"type": "string"},
        "timestamp_end": {"type": "string"},
        "elapsed_seconds": {"type": "number", "minimum": 0.0},
        "signing_algorithm": {"const": "ML-DSA-65"},
        "public_key_fingerprint": {"type": "string"},
    },
}


QUARANTINE_MANIFEST_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "schema_version",
        "migration_id",
        "phase",
        "entries",
        "signing_algorithm",
        "public_key_fingerprint",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "omnix-dm/quarantine-manifest/v1"},
        "migration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
        "phase": {"enum": ["d4_bulk", "d5_cdc"]},
        "entries": {"type": "array"},
        "signing_algorithm": {"const": "ML-DSA-65"},
        "public_key_fingerprint": {"type": "string"},
    },
}


CDC_EVENT_RECEIPT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "schema_version",
        "migration_id",
        "event_lsn",
        "relation_id",
        "table",
        "op",
        "predecessor_hash",
        "transformer_spec_hashes",
        "applied_at_target_timestamp",
        "legacy_to_target_lag_ms",
        "signing_algorithm",
        "public_key_fingerprint",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "omnix-dm/cdc-event-receipt/v1"},
        "migration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
        "event_lsn": {"type": "string", "minLength": 1},
        "relation_id": {"type": "integer", "minimum": 0},
        "table": {"type": "string", "minLength": 1},
        "op": {"enum": ["I", "U", "D", "T"]},
        "predecessor_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "transformer_spec_hashes": {"type": "array", "items": {"type": "string"}},
        "applied_at_target_timestamp": {"type": "string"},
        "legacy_to_target_lag_ms": {"type": "integer", "minimum": 0},
        "signing_algorithm": {"const": "ML-DSA-65"},
        "public_key_fingerprint": {"type": "string"},
    },
}


LAG_REPORT_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "schema_version",
        "migration_id",
        "timestamp",
        "legacy_current_lsn",
        "target_applied_lsn",
        "legacy_unreachable",
        "target_unreachable",
        "lag_lsn_bytes",
        "lag_estimated_seconds",
        "events_replayed_last_interval",
        "events_quarantined_last_interval",
        "unhandled_event_types_seen",
        "signing_algorithm",
        "public_key_fingerprint",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "omnix-dm/lag-report/v1"},
        "migration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
        "timestamp": {"type": "string"},
        "legacy_current_lsn": {"type": ["string", "null"]},
        "target_applied_lsn": {"type": ["string", "null"]},
        "legacy_unreachable": {"type": "boolean"},
        "target_unreachable": {"type": "boolean"},
        "lag_lsn_bytes": {"type": ["integer", "null"]},
        "lag_estimated_seconds": {"type": ["number", "null"]},
        "events_replayed_last_interval": {"type": "integer", "minimum": 0},
        "events_quarantined_last_interval": {"type": "integer", "minimum": 0},
        "unhandled_event_types_seen": {"type": "array", "items": {"type": "string"}},
        "signing_algorithm": {"const": "ML-DSA-65"},
        "public_key_fingerprint": {"type": "string"},
    },
}


CUTOVER_PROPOSAL_SCHEMA = {
    "$schema": "https://json-schema.org/draft/2020-12/schema",
    "type": "object",
    "required": [
        "schema_version",
        "migration_id",
        "timestamp",
        "predecessor_hash",
        "sustained_window_seconds",
        "measured_lag_seconds",
        "parity_threshold",
        "parity_metrics",
        "parity_not_met",
        "recommended_action",
        "signing_algorithm",
        "public_key_fingerprint",
    ],
    "additionalProperties": False,
    "properties": {
        "schema_version": {"const": "omnix-dm/cutover-proposal/v1"},
        "migration_id": {"type": "string", "pattern": "^[a-z0-9][a-z0-9-]*$"},
        "timestamp": {"type": "string"},
        "predecessor_hash": {"type": "string", "pattern": "^[0-9a-f]{64}$"},
        "sustained_window_seconds": {"type": "integer", "minimum": 0},
        "measured_lag_seconds": {"type": "number", "minimum": 0.0},
        "parity_threshold": {"type": "number", "minimum": 0.0, "maximum": 1.0},
        "parity_metrics": {"type": "array"},
        "parity_not_met": {"type": "boolean"},
        "recommended_action": {
            "enum": ["operator_sign", "wait_longer", "investigate_divergence"]
        },
        "operator_signoff": {"type": ["object", "null"]},
        "signing_algorithm": {"const": "ML-DSA-65"},
        "public_key_fingerprint": {"type": "string"},
    },
}


__all__ = [
    "COLUMN_MAPPING_MANIFEST_SCHEMA",
    "EDGE_CASE_MANIFEST_SCHEMA",
    "TRANSFORMER_SPEC_SCHEMA",
    "TRANSFORMER_HALT_SCHEMA",
    "BATCH_RECEIPT_SCHEMA",
    "QUARANTINE_MANIFEST_SCHEMA",
    "CDC_EVENT_RECEIPT_SCHEMA",
    "LAG_REPORT_SCHEMA",
    "CUTOVER_PROPOSAL_SCHEMA",
]
