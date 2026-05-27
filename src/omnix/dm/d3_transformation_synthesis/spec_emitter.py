"""TransformerSpec receipt emitter — schema-validated, ML-DSA-65 signed.

Reuses the PR A receipt machinery (``ml_dsa_65_signer.sign_canonical`` +
``merkle_chain.next_hash``) verbatim. Receipts land at
``.omnix/receipts/dm/prb-d3/<migration_id>/transformer-spec-<key>.json[.sig]``.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
from dataclasses import asdict
from pathlib import Path
from typing import Tuple

from jsonschema import Draft202012Validator

from omnix.crypto import ml_dsa_65
from omnix.dm._types import MFI, ReflexionSuccess, TierFailure, TransformerSpec
from omnix.dm.receipts import merkle_chain
from omnix.dm.receipts.ml_dsa_65_signer import sign_canonical
from omnix.dm.receipts.schemas import TRANSFORMER_SPEC_SCHEMA


_MID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _atomic_write(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)


def _mfi_to_dict(m: MFI) -> dict:
    return {
        "property_name": m.property_name,
        "input_value_repr": m.input_value_repr,
        "expected_output_repr": m.expected_output_repr,
        "actual_output_repr": m.actual_output_repr,
        "hint": m.hint,
    }


def _tier_failure_to_dict(t: TierFailure) -> dict:
    out = {"tier": t.tier, "reason": t.reason}
    if t.failing_mfi is not None:
        out["failing_mfi"] = _mfi_to_dict(t.failing_mfi)
    return out


def build_spec_payload(
    success: ReflexionSuccess,
    *,
    migration_id: str,
    predecessor_hash: str,
    public_key: bytes,
) -> dict:
    if not _MID_RE.match(migration_id):
        raise ValueError(
            f"migration_id must match ^[a-z0-9][a-z0-9-]*$, got {migration_id!r}"
        )
    if not _HASH_RE.match(predecessor_hash):
        raise ValueError(
            f"predecessor_hash must be 64-char hex SHA-256, got {predecessor_hash!r}"
        )
    spec = success.transformer_spec
    if spec.properties_failed:
        raise ValueError(
            "TransformerSpec.properties_failed must be empty for a Success "
            "receipt — invariant breached"
        )
    return {
        "schema_version": "omnix-dm/transformer-spec/v1",
        "migration_id": migration_id,
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "predecessor_hash": predecessor_hash,
        "column_mapping_key": spec.column_mapping_key,
        "python_source": spec.python_source,
        "sql_case": spec.sql_case,
        "datalog_rule": spec.datalog_rule,
        "properties_passed": list(spec.properties_passed),
        "properties_failed": list(spec.properties_failed),
        "mfi_history": [_mfi_to_dict(m) for m in spec.mfi_history],
        "iterations_used": spec.iterations_used,
        "cegis_pruned_sketches": list(spec.cegis_pruned_sketches),
        "tier_failures": [_tier_failure_to_dict(t) for t in spec.tier_failures],
        "tier_chosen": spec.tier_chosen,
        "confidence": round(spec.confidence, 6),
        "requires_operator_review": spec.requires_operator_review,
        "bisimulation_placeholder": dict(spec.bisimulation_placeholder),
        "signing_algorithm": "ML-DSA-65",
        "public_key_fingerprint": ml_dsa_65.fingerprint(public_key),
    }


def emit(
    success: ReflexionSuccess,
    *,
    migration_id: str,
    predecessor_hash: str,
    secret_key: bytes,
    public_key: bytes,
    output_root: Path,
) -> Path:
    """Build, schema-validate, sign, and atomically write the spec receipt.
    Returns the JSON path; signature is written alongside as ``<name>.sig``."""
    payload = build_spec_payload(
        success,
        migration_id=migration_id,
        predecessor_hash=predecessor_hash,
        public_key=public_key,
    )
    Draft202012Validator(TRANSFORMER_SPEC_SCHEMA).validate(payload)
    canonical, sig_hex = sign_canonical(payload, secret_key)

    key = success.transformer_spec.column_mapping_key
    out_dir = Path(output_root) / migration_id
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"transformer-spec-{key}.json"
    sig_path = out_dir / f"transformer-spec-{key}.json.sig"
    chain_path = out_dir / f"transformer-spec-{key}.chainhash"

    _atomic_write(json_path, canonical)
    _atomic_write(sig_path, sig_hex.encode("ascii"))
    chain_hash = merkle_chain.next_hash(predecessor_hash, canonical)
    _atomic_write(chain_path, chain_hash.encode("ascii"))
    return json_path


__all__ = ["build_spec_payload", "emit"]
