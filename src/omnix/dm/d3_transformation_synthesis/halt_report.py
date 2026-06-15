"""HaltReport emitter — schema-validated, ML-DSA-65 signed.

Emitted when the Reflexion loop cannot synthesize a passing transformer for
a given ColumnMapping. The receipt captures every failing MFI, the latest
attempted Python source, the last critique, and (if applicable) the
SecurityViolation that triggered the halt.

Honesty invariant: synthesis NEVER silently substitutes an identity transformer when
synthesis halts. The halt is a first-class signed receipt the operator must
adjudicate.
"""

from __future__ import annotations

import datetime as _dt
import os
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from omnix.crypto import ml_dsa_65
from omnix.dm._types import MFI, ReflexionHalt, SecurityViolation
from omnix.dm.receipts import merkle_chain
from omnix.dm.receipts.ml_dsa_65_signer import sign_canonical
from omnix.dm.receipts.schemas import TRANSFORMER_HALT_SCHEMA

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


def _sv_to_dict(sv: SecurityViolation) -> dict:
    return {
        "node_type": sv.node_type,
        "reason": sv.reason,
        "source_excerpt": sv.source_excerpt,
    }


def build_halt_payload(
    halt: ReflexionHalt,
    *,
    migration_id: str,
    predecessor_hash: str,
    public_key: bytes,
) -> dict:
    if not _MID_RE.match(migration_id):
        raise ValueError(f"migration_id invalid: {migration_id!r}")
    if not _HASH_RE.match(predecessor_hash):
        raise ValueError(f"predecessor_hash invalid: {predecessor_hash!r}")
    return {
        "schema_version": "omnix-dm/transformer-halt/v1",
        "migration_id": migration_id,
        "timestamp": _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "predecessor_hash": predecessor_hash,
        "column_mapping_key": halt.column_mapping_key,
        "halt_reason": halt.halt_reason,
        "latest_python_source": halt.latest_python_source,
        "failing_mfis": [_mfi_to_dict(m) for m in halt.failing_mfis],
        "last_critique": halt.last_critique,
        "iterations_used": halt.iterations_used,
        "security_violation": _sv_to_dict(halt.security_violation)
        if halt.security_violation is not None
        else None,
        "signing_algorithm": "ML-DSA-65",
        "public_key_fingerprint": ml_dsa_65.fingerprint(public_key),
    }


def emit_halt(
    halt: ReflexionHalt,
    *,
    migration_id: str,
    predecessor_hash: str,
    secret_key: bytes,
    public_key: bytes,
    output_root: Path,
) -> Path:
    payload = build_halt_payload(
        halt,
        migration_id=migration_id,
        predecessor_hash=predecessor_hash,
        public_key=public_key,
    )
    Draft202012Validator(TRANSFORMER_HALT_SCHEMA).validate(payload)
    canonical, sig_hex = sign_canonical(payload, secret_key)

    key = halt.column_mapping_key
    out_dir = Path(output_root) / migration_id
    out_dir.mkdir(parents=True, exist_ok=True)
    json_path = out_dir / f"transformer-halt-{key}.json"
    sig_path = out_dir / f"transformer-halt-{key}.json.sig"
    chain_path = out_dir / f"transformer-halt-{key}.chainhash"

    _atomic_write(json_path, canonical)
    _atomic_write(sig_path, sig_hex.encode("ascii"))
    chain_hash = merkle_chain.next_hash(predecessor_hash, canonical)
    _atomic_write(chain_path, chain_hash.encode("ascii"))
    return json_path


__all__ = ["build_halt_payload", "emit_halt"]
