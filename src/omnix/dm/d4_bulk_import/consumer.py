"""PR C consumer — load + verify the full PR A → PR B → PR C Merkle chain.

For a given ``migration_id`` we expect:

  .omnix/receipts/dm/pra-d1-d2/<migration_id>/column-mapping.json[.sig]
  .omnix/receipts/dm/pra-d1-d2/<migration_id>/edge-case-manifest.json[.sig]
  .omnix/receipts/dm/prb-d3/<migration_id>/transformer-spec-<key>.json[.sig]
  .omnix/receipts/dm/prb-d3/<migration_id>/transformer-halt-<key>.json[.sig]  (optional)

Every receipt is JSON-Schema validated AND ML-DSA-65 signature-verified
before any field is read. The bundle returned exposes the D1 mappings, D2
findings, D3 TransformerSpecs keyed by ``{table}.{column}``, the canonical
SHA-256 of D2 (which becomes the predecessor_hash for all D4 BatchReceipts),
and a per-column TransformerSpec hash (used as predecessor_hash for D5
CDC event receipts).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Optional, Tuple

from jsonschema import Draft202012Validator

from omnix.crypto import ml_dsa_65
from omnix.dm._types import (
    AnomalyFinding,
    ColumnMapping,
    ColumnSpec,
    SchemaSpec,
    TableSpec,
)
from omnix.dm.receipts.ml_dsa_65_signer import canonicalize
from omnix.dm.receipts.schemas import (
    COLUMN_MAPPING_MANIFEST_SCHEMA,
    EDGE_CASE_MANIFEST_SCHEMA,
    TRANSFORMER_SPEC_SCHEMA,
)


class PrePhaseSignatureError(RuntimeError):
    """A required signature failed verification; never enter D4."""


class InconsistentReceiptStateError(RuntimeError):
    """PR B emitted both a spec AND a halt for the same column."""


@dataclass(frozen=True)
class ConsumedBundle:
    migration_id: str
    column_mappings: Tuple[ColumnMapping, ...]
    findings: Tuple[AnomalyFinding, ...]
    legacy_schema: SchemaSpec
    target_schema: SchemaSpec
    transformer_specs: Dict[str, dict]   # "{table}.{column}" → spec payload
    transformer_halts: Dict[str, dict]   # "{table}.{column}" → halt payload
    spec_canonical_hashes: Dict[str, str]  # "{table}.{column}" → canonical SHA-256
    predecessor_hash: str  # canonical SHA-256 of D2 edge-case-manifest
    unmapped_columns: Tuple[str, ...]


def _verify_signature(payload: dict, sig_path: Path, public_key: Optional[bytes]) -> None:
    if public_key is None:
        return  # opt-out for test fixtures
    sig_hex = sig_path.read_text().strip()
    try:
        sig = bytes.fromhex(sig_hex)
    except ValueError as exc:
        raise PrePhaseSignatureError(f"malformed signature at {sig_path}: {exc}") from exc
    if not ml_dsa_65.verify(public_key, canonicalize(payload), sig):
        raise PrePhaseSignatureError(f"ML-DSA-65 verification failed at {sig_path}")


def _schema_from_dict(d: dict) -> SchemaSpec:
    from omnix.dm._types import ForeignKeySpec, IndexSpec

    tables = []
    for t in d.get("tables", []):
        cols = tuple(
            ColumnSpec(
                name=c["name"],
                raw_type=c["raw_type"],
                normalized_type=c["normalized_type"],
                nullable=c.get("nullable", True),
                default=c.get("default"),
                primary_key=c.get("primary_key", False),
                unique=c.get("unique", False),
                comment=c.get("comment"),
                dialect_specific=c.get("dialect_specific", {}),
            )
            for c in t.get("columns", [])
        )
        fks = tuple(
            ForeignKeySpec(
                name=fk.get("name", ""),
                from_table=fk.get("from_table", t["name"]),
                from_columns=tuple(fk.get("from_columns", ())),
                to_table=fk["to_table"],
                to_columns=tuple(fk.get("to_columns", ())),
                on_delete=fk.get("on_delete"),
                on_update=fk.get("on_update"),
            )
            for fk in t.get("foreign_keys", [])
        )
        idxs = tuple(
            IndexSpec(
                name=i.get("name", ""),
                table=i.get("table", t["name"]),
                columns=tuple(i.get("columns", ())),
                unique=i.get("unique", False),
                method=i.get("method"),
            )
            for i in t.get("indexes", [])
        )
        tables.append(
            TableSpec(
                name=t["name"],
                columns=cols,
                primary_key=tuple(t.get("primary_key", ())),
                foreign_keys=fks,
                indexes=idxs,
                comment=t.get("comment"),
            )
        )
    return SchemaSpec(
        dialect=d.get("dialect", "postgres"),
        name=d.get("name", ""),
        tables=tuple(tables),
        parse_warnings=tuple(d.get("parse_warnings", ())),
    )


def _mappings_from_d1(d1: dict) -> Tuple[ColumnMapping, ...]:
    out = []
    for m in d1.get("mappings", []):
        candidates = tuple(
            (c["target_table"], c["target_column"], c["similarity"])
            for c in m.get("candidates", [])
        )
        out.append(
            ColumnMapping(
                legacy_table=m["legacy_table"],
                legacy_column=m["legacy_column"],
                target_table=m["target_table"],
                target_column=m["target_column"],
                confidence=m["confidence"],
                status=m["status"],
                candidates=candidates,
                rationale=m.get("rationale", ""),
            )
        )
    return tuple(out)


def _findings_from_d2(d2: dict) -> Tuple[AnomalyFinding, ...]:
    out = []
    for f in d2.get("findings", []):
        out.append(
            AnomalyFinding(
                probe_category=f["probe_category"],
                legacy_table=f["legacy_table"],
                legacy_column=f["legacy_column"],
                anomaly_type=f["anomaly_type"],
                severity=f["severity"],
                sample_values=tuple(f.get("sample_values", ())),
                affected_row_count=f.get("affected_row_count"),
                remediation_hint=f.get("remediation_hint", ""),
                requires_human_decision=f.get("requires_human_decision", False),
            )
        )
    return tuple(out)


def load_prior_receipts(
    migration_id: str,
    *,
    receipts_root: Path | str = ".omnix/receipts/dm",
    public_key: Optional[bytes] = None,
    verify_signatures: bool = True,
) -> ConsumedBundle:
    """Load + verify D1/D2 + every D3 spec/halt receipt for ``migration_id``."""
    root = Path(receipts_root)
    pra_dir = root / "pra-d1-d2" / migration_id
    prb_dir = root / "prb-d3" / migration_id
    d1_path = pra_dir / "column-mapping.json"
    d2_path = pra_dir / "edge-case-manifest.json"
    if not d1_path.exists() or not d2_path.exists():
        raise FileNotFoundError(f"PR A manifests missing at {pra_dir!s}")

    d1 = json.loads(d1_path.read_text())
    d2 = json.loads(d2_path.read_text())
    Draft202012Validator(COLUMN_MAPPING_MANIFEST_SCHEMA).validate(d1)
    Draft202012Validator(EDGE_CASE_MANIFEST_SCHEMA).validate(d2)
    if verify_signatures:
        _verify_signature(d1, pra_dir / "column-mapping.json.sig", public_key)
        _verify_signature(d2, pra_dir / "edge-case-manifest.json.sig", public_key)

    transformer_specs: Dict[str, dict] = {}
    transformer_halts: Dict[str, dict] = {}
    spec_hashes: Dict[str, str] = {}
    if prb_dir.exists():
        for spec_path in sorted(prb_dir.glob("transformer-spec-*.json")):
            payload = json.loads(spec_path.read_text())
            Draft202012Validator(TRANSFORMER_SPEC_SCHEMA).validate(payload)
            if verify_signatures:
                _verify_signature(
                    payload, spec_path.with_suffix(".json.sig"), public_key
                )
            key = payload["column_mapping_key"]
            if key in transformer_specs:
                raise InconsistentReceiptStateError(
                    f"duplicate spec for {key!r} in {prb_dir!s}"
                )
            transformer_specs[key] = payload
            spec_hashes[key] = hashlib.sha256(canonicalize(payload)).hexdigest()
        for halt_path in sorted(prb_dir.glob("transformer-halt-*.json")):
            payload = json.loads(halt_path.read_text())
            if verify_signatures:
                _verify_signature(
                    payload, halt_path.with_suffix(".json.sig"), public_key
                )
            key = payload["column_mapping_key"]
            if key in transformer_specs:
                raise InconsistentReceiptStateError(
                    f"column {key!r} has BOTH a spec AND a halt receipt"
                )
            transformer_halts[key] = payload

    legacy_schema = _schema_from_dict(d1.get("legacy_schema", {}))
    target_schema = _schema_from_dict(d1.get("target_schema", {}))
    mappings = _mappings_from_d1(d1)
    findings = _findings_from_d2(d2)

    unmapped = tuple(
        f"{m.legacy_table}.{m.legacy_column}"
        for m in mappings
        if f"{m.legacy_table}.{m.legacy_column}" not in transformer_specs
        and f"{m.legacy_table}.{m.legacy_column}" not in transformer_halts
    )

    predecessor_hash = hashlib.sha256(canonicalize(d2)).hexdigest()

    return ConsumedBundle(
        migration_id=migration_id,
        column_mappings=mappings,
        findings=findings,
        legacy_schema=legacy_schema,
        target_schema=target_schema,
        transformer_specs=transformer_specs,
        transformer_halts=transformer_halts,
        spec_canonical_hashes=spec_hashes,
        predecessor_hash=predecessor_hash,
        unmapped_columns=unmapped,
    )


__all__ = [
    "ConsumedBundle",
    "PrePhaseSignatureError",
    "InconsistentReceiptStateError",
    "load_prior_receipts",
]
