"""Row / Batch / TransformedBatch primitives + deterministic batch_id.

JSON serialisation reuses the encoding hooks from PR B's sandbox_runner so
datetime/Decimal/bytes survive the IPC round-trip into worker subprocesses
without lossy reprs.
"""

from __future__ import annotations

import datetime
import decimal
import hashlib
import json
import re
from typing import Any, Dict, Tuple

from omnix.dm._types import Batch, Row, TransformedBatch, TransformedRow

_MID_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def make_batch_id(migration_id: str, table: str, batch_no: int) -> str:
    """Deterministic ``sha256(migration_id || '|' || table || '|' || batch_no)``.

    Identical inputs at two construction sites produce identical batch_ids —
    this is the idempotency contract.
    """
    if not _MID_RE.match(migration_id):
        raise ValueError(
            f"migration_id must match ^[a-z0-9][a-z0-9-]*$, got {migration_id!r}"
        )
    digest = hashlib.sha256(f"{migration_id}|{table}|{batch_no}".encode("utf-8"))
    return digest.hexdigest()


def normalize_row(
    legacy_table: str,
    pk_value_repr: str,
    raw_columns: Dict[str, Any],
) -> Row:
    """Return a Row whose ``column_values`` tuple is sorted by column name so
    that two Rows with the same data produce identical reprs regardless of
    dict iteration order."""
    items = tuple(sorted(raw_columns.items(), key=lambda kv: kv[0]))
    return Row(
        legacy_table=legacy_table,
        pk_value_repr=pk_value_repr,
        column_values=items,
    )


# JSON encoding hooks — mirror PR B's sandbox_runner ``_to_json_safe`` /
# ``_decode_input`` pair so the subprocess workers see live datetimes etc.

def _encode_value(v: Any) -> Any:
    if v is None or isinstance(v, (bool, int, float, str)):
        return v
    if isinstance(v, datetime.datetime):
        return {"__datetime__": v.isoformat()}
    if isinstance(v, datetime.date):
        return {"__date__": v.isoformat()}
    if isinstance(v, decimal.Decimal):
        return {"__decimal__": str(v)}
    if isinstance(v, (bytes, bytearray)):
        return {"__bytes__": bytes(v).hex()}
    if isinstance(v, (list, tuple)):
        return [_encode_value(x) for x in v]
    if isinstance(v, dict):
        return {str(k): _encode_value(x) for k, x in v.items()}
    return repr(v)


def _decode_value(v: Any) -> Any:
    if isinstance(v, dict):
        if "__datetime__" in v:
            return datetime.datetime.fromisoformat(v["__datetime__"])
        if "__date__" in v:
            return datetime.date.fromisoformat(v["__date__"])
        if "__decimal__" in v:
            return decimal.Decimal(v["__decimal__"])
        if "__bytes__" in v:
            return bytes.fromhex(v["__bytes__"])
        return {k: _decode_value(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_decode_value(x) for x in v]
    return v


def serialize_batch(batch: Batch) -> bytes:
    payload = {
        "migration_id": batch.migration_id,
        "table": batch.table,
        "batch_no": batch.batch_no,
        "batch_id": batch.batch_id,
        "snapshot_lsn": batch.snapshot_lsn,
        "rows": [
            {
                "legacy_table": r.legacy_table,
                "pk_value_repr": r.pk_value_repr,
                "column_values": [
                    [name, _encode_value(value)] for (name, value) in r.column_values
                ],
            }
            for r in batch.rows
        ],
    }
    return json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")


def deserialize_batch(data: bytes) -> Batch:
    payload = json.loads(data.decode("utf-8"))
    rows = tuple(
        Row(
            legacy_table=r["legacy_table"],
            pk_value_repr=r["pk_value_repr"],
            column_values=tuple(
                (name, _decode_value(value))
                for (name, value) in r["column_values"]
            ),
        )
        for r in payload["rows"]
    )
    return Batch(
        migration_id=payload["migration_id"],
        table=payload["table"],
        batch_no=payload["batch_no"],
        batch_id=payload["batch_id"],
        rows=rows,
        snapshot_lsn=payload.get("snapshot_lsn"),
    )


__all__ = [
    "make_batch_id",
    "normalize_row",
    "serialize_batch",
    "deserialize_batch",
]
