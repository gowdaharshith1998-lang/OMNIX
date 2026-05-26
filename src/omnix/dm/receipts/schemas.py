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


__all__ = [
    "COLUMN_MAPPING_MANIFEST_SCHEMA",
    "EDGE_CASE_MANIFEST_SCHEMA",
]
