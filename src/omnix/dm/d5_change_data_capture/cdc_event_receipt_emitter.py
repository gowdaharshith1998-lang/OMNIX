"""Sampled CDCEventReceipt emitter.

PR C samples at ``OMNIX_DM_CDC_EVENT_RECEIPT_SAMPLE_RATE`` (default 0.01)
because emitting one signed receipt per event at OLTP scale (10K-100K/s)
would dominate runtime. The durable proof of replay is the target row +
``__omnix_cdc_lsn`` watermark; the sampled receipts are for audit. Set
the rate to ``1.0`` for compliance pilots that require full receipt.
"""

from __future__ import annotations

import datetime
import hashlib
import os
import random
import re
from pathlib import Path

from jsonschema import Draft202012Validator

from omnix.crypto import ml_dsa_65
from omnix.dm._types import CDCEventReceipt
from omnix.dm.receipts.ml_dsa_65_signer import sign_canonical
from omnix.dm.receipts.schemas import CDC_EVENT_RECEIPT_SCHEMA


_HASH_RE = re.compile(r"^[0-9a-f]{64}$")


def _atomic_write(target: Path, payload: bytes) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    with open(tmp, "wb") as fh:
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, target)


def sample_rate() -> float:
    try:
        return float(os.environ.get("OMNIX_DM_CDC_EVENT_RECEIPT_SAMPLE_RATE", "0.01"))
    except ValueError:
        return 0.01


def should_emit(rng: random.Random | None = None) -> bool:
    rate = sample_rate()
    if rate <= 0.0:
        return False
    if rate >= 1.0:
        return True
    r = rng if rng is not None else random
    return r.random() < rate


def emit(
    receipt: CDCEventReceipt,
    *,
    secret_key: bytes,
    public_key: bytes,
    output_root: Path,
) -> Path:
    if not _HASH_RE.match(receipt.predecessor_hash):
        raise ValueError(
            f"predecessor_hash must be 64-char hex, got {receipt.predecessor_hash!r}"
        )
    payload = {
        "schema_version": "omnix-dm/cdc-event-receipt/v1",
        "migration_id": receipt.migration_id,
        "event_lsn": receipt.event_lsn,
        "relation_id": receipt.relation_id,
        "table": receipt.table,
        "op": receipt.op,
        "predecessor_hash": receipt.predecessor_hash,
        "transformer_spec_hashes": list(receipt.transformer_spec_hashes),
        "applied_at_target_timestamp": receipt.applied_at_target_timestamp,
        "legacy_to_target_lag_ms": receipt.legacy_to_target_lag_ms,
        "signing_algorithm": "ML-DSA-65",
        "public_key_fingerprint": ml_dsa_65.fingerprint(public_key),
    }
    Draft202012Validator(CDC_EVENT_RECEIPT_SCHEMA).validate(payload)
    canonical, sig_hex = sign_canonical(payload, secret_key)
    out_dir = Path(output_root) / receipt.migration_id / "d5"
    safe_lsn = receipt.event_lsn.replace("/", "-")
    json_path = out_dir / f"cdc-event-receipt-{safe_lsn}.json"
    sig_path = out_dir / f"cdc-event-receipt-{safe_lsn}.json.sig"
    _atomic_write(json_path, canonical)
    _atomic_write(sig_path, sig_hex.encode("ascii"))
    return json_path


__all__ = ["sample_rate", "should_emit", "emit"]
