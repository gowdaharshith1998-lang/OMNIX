"""D1 mapping emitter — atomic, ML-DSA-65 signed, JSON-Schema validated.

Contract:
  * ``emit`` returns the Path of the written manifest. The .sig file lives
    alongside.
  * Sign-then-write-both is atomic in the practical sense: we write to a
    temp file, fsync, then rename. If signing fails, nothing is written.
  * JSON Schema validation runs **before** signing — a malformed payload
    never gets a signature attached.
"""

from __future__ import annotations

import dataclasses
import datetime as _dt
import os
from pathlib import Path
from typing import Optional, Tuple

from jsonschema import Draft202012Validator

from omnix.crypto import ml_dsa_65
from omnix.dm._types import ColumnMapping, SchemaSpec
from omnix.dm.receipts import merkle_chain
from omnix.dm.receipts.ml_dsa_65_signer import canonicalize, sign_canonical
from omnix.dm.receipts.schemas import COLUMN_MAPPING_MANIFEST_SCHEMA


def _schema_to_dict(spec: SchemaSpec) -> dict:
    """Render a SchemaSpec as plain dict for the manifest. Frozen dataclasses
    are converted via dataclasses.asdict; tuples become lists for JSON."""
    return dataclasses.asdict(spec)


def _mapping_to_dict(m: ColumnMapping) -> dict:
    return {
        "legacy_table": m.legacy_table,
        "legacy_column": m.legacy_column,
        "target_table": m.target_table,
        "target_column": m.target_column,
        "confidence": round(m.confidence, 6),
        "status": m.status,
        "candidates": [
            {"target_table": t, "target_column": c, "similarity": round(s, 6)}
            for (t, c, s) in m.candidates
        ],
        "rationale": m.rationale,
    }


def _atomic_write(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "wb") as f:
        f.write(payload)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, target)


def _now_iso() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def build_manifest(
    mappings: Tuple[ColumnMapping, ...],
    legacy: SchemaSpec,
    target: SchemaSpec,
    migration_id: str,
    predecessor_hash: Optional[str],
    public_key: bytes,
) -> dict:
    """Construct the dict (un-signed) version of the column-mapping manifest."""
    stats = {
        "total_legacy_columns": len(mappings),
        "status_ok_count": sum(1 for m in mappings if m.status == "ok"),
        "status_low_confidence_count": sum(
            1 for m in mappings if m.status == "low_confidence"
        ),
        "status_ambiguous_count": sum(1 for m in mappings if m.status == "ambiguous"),
        "status_no_match_count": sum(1 for m in mappings if m.status == "no_match"),
    }
    requires_review = stats["status_low_confidence_count"] > 0 or stats["status_ambiguous_count"] > 0 or stats["status_no_match_count"] > 0
    payload = {
        "schema_version": "omnix-dm/column-mapping/v1",
        "migration_id": migration_id,
        "timestamp": _now_iso(),
        "legacy_schema": _schema_to_dict(legacy),
        "target_schema": _schema_to_dict(target),
        "mappings": [_mapping_to_dict(m) for m in mappings],
        "predecessor_hash": predecessor_hash,
        "stats": stats,
        "signing_algorithm": "ML-DSA-65",
        "public_key_fingerprint": ml_dsa_65.fingerprint(public_key),
        "requires_operator_review": requires_review,
    }
    return payload


_MID_RE = __import__("re").compile(r"^[a-z0-9][a-z0-9-]*$")


def emit(
    mappings: Tuple[ColumnMapping, ...],
    legacy: SchemaSpec,
    target: SchemaSpec,
    migration_id: str,
    secret_key: bytes,
    public_key: bytes,
    output_root: Path,
    predecessor_hash: Optional[str] = None,
) -> Path:
    """Validate, sign, and atomically write the column-mapping manifest.

    Returns the Path of the written JSON. Signature is written alongside as
    ``<manifest>.sig`` (hex-encoded ML-DSA-65 signature)."""
    if not _MID_RE.match(migration_id):
        raise ValueError(
            f"migration_id must match ^[a-z0-9][a-z0-9-]*$, got {migration_id!r}"
        )

    manifest = build_manifest(
        mappings, legacy, target, migration_id, predecessor_hash, public_key
    )
    Draft202012Validator(COLUMN_MAPPING_MANIFEST_SCHEMA).validate(manifest)
    canonical, sig_hex = sign_canonical(manifest, secret_key)

    out_dir = Path(output_root) / migration_id
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / "column-mapping.json"
    sig_path = out_dir / "column-mapping.json.sig"
    chain_path = out_dir / "column-mapping.chainhash"

    _atomic_write(json_path, canonical)
    _atomic_write(sig_path, sig_hex.encode("ascii"))
    chain_hash = merkle_chain.next_hash(predecessor_hash, canonical)
    _atomic_write(chain_path, chain_hash.encode("ascii"))
    return json_path


__all__ = [
    "build_manifest",
    "emit",
]
