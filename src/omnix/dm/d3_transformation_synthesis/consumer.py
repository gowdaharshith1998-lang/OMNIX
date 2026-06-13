"""Consumer for PR A signed manifests.

D3 reads (never writes) two manifests from
``.omnix/receipts/dm/pra-d1-d2/<migration_id>/``:

  * ``column-mapping.json`` + ``.sig`` — D1 output
  * ``edge-case-manifest.json`` + ``.sig`` — D2 output

At load time we verify the ML-DSA-65 signatures via
``omnix.crypto.ml_dsa_65.verify`` and validate the JSON Schema. If either
fails: HALT. Never enter the synthesis loop with unverified PR A output.

We compute the canonical SHA-256 of the D2 manifest and surface it as
``predecessor_hash`` — every TransformerSpec receipt chains directly to D2.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

from jsonschema import Draft202012Validator

from omnix.crypto import ml_dsa_65
from omnix.dm._types import (
    AnomalyFinding,
    ColumnMapping,
    ColumnSpec,
)
from omnix.dm.receipts import merkle_chain
from omnix.dm.receipts.ml_dsa_65_signer import canonicalize
from omnix.dm.receipts.schemas import (
    COLUMN_MAPPING_MANIFEST_SCHEMA,
    EDGE_CASE_MANIFEST_SCHEMA,
)


class ConsumerHalt(RuntimeError):
    """Raised when PR A manifest verification fails. Never proceed."""


@dataclass(frozen=True)
class ConsumedManifests:
    column_mappings: Tuple[ColumnMapping, ...]
    findings: Tuple[AnomalyFinding, ...]
    column_specs: Dict[str, ColumnSpec]  # "{table}.{column}" → ColumnSpec
    target_column_specs: Dict[str, ColumnSpec]
    predecessor_hash: str  # SHA-256 of D2 manifest canonical JSON
    migration_id: str


def _verify_signature(
    payload: dict, sig_path: Path, public_key: Optional[bytes]
) -> None:
    if public_key is None:
        return  # caller opted out (test fixtures)
    sig_hex = sig_path.read_text(encoding="utf-8").strip()
    try:
        sig = bytes.fromhex(sig_hex)
    except ValueError as exc:
        raise ConsumerHalt(f"malformed signature at {sig_path}: {exc}") from exc
    canonical = canonicalize(payload)
    if not ml_dsa_65.verify(public_key, canonical, sig):
        raise ConsumerHalt(f"ML-DSA-65 signature verification failed at {sig_path}")


def _findings_from_d2(d2: dict) -> Tuple[AnomalyFinding, ...]:
    out: List[AnomalyFinding] = []
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


def _mappings_from_d1(d1: dict) -> Tuple[ColumnMapping, ...]:
    out: List[ColumnMapping] = []
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


def _column_specs_from_schema(schema_dict: dict) -> Dict[str, ColumnSpec]:
    """Walk a serialized SchemaSpec dict (``dataclasses.asdict`` shape) and
    rebuild ColumnSpec instances keyed by ``{table}.{column}``."""
    out: Dict[str, ColumnSpec] = {}
    for t in schema_dict.get("tables", []):
        table_name = t["name"]
        for c in t.get("columns", []):
            cs = ColumnSpec(
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
            out[f"{table_name}.{c['name']}"] = cs
    return out


def load_manifests(
    manifest_root: Path,
    migration_id: str,
    *,
    public_key: Optional[bytes] = None,
    verify_signatures: bool = True,
) -> ConsumedManifests:
    """Load + verify the PR A manifests under ``manifest_root/migration_id/``.

    ``verify_signatures=False`` skips ML-DSA verification (test fixtures);
    JSON Schema validation always runs.
    """
    base = Path(manifest_root) / migration_id
    d1_path = base / "column-mapping.json"
    d2_path = base / "edge-case-manifest.json"
    d1_sig = base / "column-mapping.json.sig"
    d2_sig = base / "edge-case-manifest.json.sig"
    if not d1_path.exists() or not d2_path.exists():
        raise ConsumerHalt(
            f"PR A manifests missing at {base!s}: column-mapping + edge-case-manifest"
        )

    # Receipts are written as UTF-8 (ensure_ascii=False); they MUST be read
    # back as UTF-8 or non-ASCII content (e.g. an em-dash in a parse warning)
    # is mojibake'd on platforms whose default text encoding is not UTF-8
    # (Windows cp1252), corrupting both signature verification and the
    # predecessor-hash chain link.
    d1 = json.loads(d1_path.read_text(encoding="utf-8"))
    d2 = json.loads(d2_path.read_text(encoding="utf-8"))
    Draft202012Validator(COLUMN_MAPPING_MANIFEST_SCHEMA).validate(d1)
    Draft202012Validator(EDGE_CASE_MANIFEST_SCHEMA).validate(d2)
    if verify_signatures:
        if public_key is None:
            # Fail closed: asking for verification without a key previously
            # skipped silently, defeating the entire trust gate.
            raise ConsumerHalt(
                "verify_signatures=True requires a public_key; refusing to "
                "proceed with unverifiable PR A manifests"
            )
        _verify_signature(d1, d1_sig, public_key)
        _verify_signature(d2, d2_sig, public_key)

    # Validate the D1->D2 Merkle link. Each manifest's chain hash is
    # next_hash(predecessor_hash, canonical(manifest)) — the value every
    # emitter writes to its .chainhash file. The edge-case (D2) manifest must
    # carry the column-mapping (D1) manifest's chain hash as its
    # predecessor_hash; otherwise a substituted or reordered D1/D2 pair whose
    # individual signatures still verify would be accepted. This is the chain
    # integrity check the receipts previously signed but never enforced.
    expected_d2_predecessor = merkle_chain.next_hash(
        d1.get("predecessor_hash"), canonicalize(d1)
    )
    if d2.get("predecessor_hash") != expected_d2_predecessor:
        raise ConsumerHalt(
            "D1->D2 Merkle chain link broken: edge-case manifest predecessor_hash "
            "does not equal the column-mapping manifest's chain hash"
        )

    canonical_d2 = canonicalize(d2)
    predecessor_hash = hashlib.sha256(canonical_d2).hexdigest()
    return ConsumedManifests(
        column_mappings=_mappings_from_d1(d1),
        findings=_findings_from_d2(d2),
        column_specs=_column_specs_from_schema(d1.get("legacy_schema", {})),
        target_column_specs=_column_specs_from_schema(d1.get("target_schema", {})),
        predecessor_hash=predecessor_hash,
        migration_id=migration_id,
    )


def findings_for(
    findings: Iterable[AnomalyFinding],
    mapping: ColumnMapping,
) -> Tuple[AnomalyFinding, ...]:
    return tuple(
        f
        for f in findings
        if f.legacy_table == mapping.legacy_table
        and f.legacy_column == mapping.legacy_column
    )


__all__ = ["ConsumerHalt", "ConsumedManifests", "load_manifests", "findings_for"]
