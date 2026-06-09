"""BatchReceipt emitter — schema-validated, ML-DSA-65 signed, atomic."""

from __future__ import annotations

import hashlib
import os
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from omnix.crypto import ml_dsa_65
from omnix.dm._types import BatchReceipt
from omnix.dm.receipts.ml_dsa_65_signer import sign_canonical
from omnix.dm.receipts.schemas import BATCH_RECEIPT_SCHEMA

_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def db_fingerprint(user: str, host: str, port: int, database: str) -> str:
    """Return ``sha256("user@host:port/database")`` — used in receipts so the
    audit trail can identify which target was written without leaking the
    password."""
    return hashlib.sha256(
        f"{user}@{host}:{port}/{database}".encode("utf-8")
    ).hexdigest()


def _atomic_write(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)


def emit(
    receipt: BatchReceipt,
    *,
    secret_key: bytes,
    public_key: bytes,
    output_root: Path,
) -> Path:
    if not _HASH_RE.match(receipt.batch_id):
        raise ValueError(f"batch_id must be 64-char hex, got {receipt.batch_id!r}")
    if not _HASH_RE.match(receipt.predecessor_hash):
        raise ValueError(
            f"predecessor_hash must be 64-char hex SHA-256, got {receipt.predecessor_hash!r}"
        )
    payload = {
        "schema_version": "omnix-dm/batch-receipt/v1",
        "migration_id": receipt.migration_id,
        "table": receipt.table,
        "batch_no": receipt.batch_no,
        "batch_id": receipt.batch_id,
        "predecessor_hash": receipt.predecessor_hash,
        "rows_read": receipt.rows_read,
        "rows_written": receipt.rows_written,
        "rows_quarantined": receipt.rows_quarantined,
        "quarantine_offsets": list(receipt.quarantine_offsets),
        "transformer_spec_hashes": list(receipt.transformer_spec_hashes),
        "target_db_fingerprint": receipt.target_db_fingerprint,
        "timestamp_start": receipt.timestamp_start,
        "timestamp_end": receipt.timestamp_end,
        "elapsed_seconds": round(receipt.elapsed_seconds, 6),
        "signing_algorithm": "ML-DSA-65",
        "public_key_fingerprint": ml_dsa_65.fingerprint(public_key),
    }
    Draft202012Validator(BATCH_RECEIPT_SCHEMA).validate(payload)
    canonical, sig_hex = sign_canonical(payload, secret_key)
    target_dir = Path(output_root) / receipt.migration_id / "d4"
    json_path = target_dir / f"batch-receipt-{receipt.table}-{receipt.batch_no}.json"
    sig_path = target_dir / f"batch-receipt-{receipt.table}-{receipt.batch_no}.json.sig"
    _atomic_write(json_path, canonical)
    _atomic_write(sig_path, sig_hex.encode("ascii"))
    return json_path


__all__ = ["db_fingerprint", "emit"]
