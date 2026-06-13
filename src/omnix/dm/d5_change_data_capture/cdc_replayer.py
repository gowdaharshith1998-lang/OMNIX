"""CDC replayer — apply each ChangeEvent through PR B's TransformerSpec to
the target DB, with sampled receipts + quarantine on failure.

Idempotency: each event writes a ``__omnix_cdc_lsn`` watermark column; on
re-delivery (the same LSN landing twice), the replayer skips with an
``idempotent_skip`` counter increment. Watermark advancement only happens
AFTER the target write commits — never before — so a crash mid-event
leaves an unconfirmed event in the WAL and the slot still pointing at it.
"""

from __future__ import annotations

import datetime
import hashlib
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

from omnix.dm._types import (
    CDCEventQuarantineEntry,
    CDCEventReceipt,
    ChangeEvent,
)
from omnix.dm.d3_transformation_synthesis.transformer_dsl import (
    ExecutionSuccess,
    _SecurityViolationError,
    execute,
)
from omnix.dm.d5_change_data_capture import cdc_event_receipt_emitter
from omnix.dm.d5_change_data_capture.cdc_quarantine import CDCQuarantineLog


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


@dataclass
class CDCReplayState:
    """Live counters surfaced for the lag monitor."""

    migration_id: str
    events_replayed: int = 0
    events_quarantined: int = 0
    events_idempotent_skipped: int = 0
    receipts_emitted: int = 0
    last_applied_lsn: Optional[str] = None
    unhandled_event_types: List[str] = field(default_factory=list)


def _hash_lsn(lsn: str) -> int:
    """Crude monotonic comparator for LSNs — converts ``X/YYYY`` to a
    sortable int. Sufficient for idempotency comparison; the live PG
    adapter would use ``pg_lsn`` for ordering."""
    if "/" not in lsn:
        return 0
    hi, lo = lsn.split("/", 1)
    try:
        return (int(hi, 16) << 32) | int(lo, 16)
    except ValueError:
        return 0


def _watermark_tuple(watermark: str) -> Tuple[int, int]:
    """Decode a ``lsn#seq`` watermark into a comparable (lsn, seq) pair.
    Plain-LSN watermarks (pre-seq format) decode with seq=0."""
    lsn, _, seq = watermark.partition("#")
    try:
        return (_hash_lsn(lsn), int(seq or 0))
    except ValueError:
        return (_hash_lsn(lsn), 0)


def _qident(name: str) -> str:
    """Quote a SQL identifier; reject injection-capable names outright."""
    if '"' in name or "\x00" in name:
        raise ValueError(f"invalid identifier: {name!r}")
    return f'"{name}"'


def replay_one(
    event: ChangeEvent,
    *,
    state: CDCReplayState,
    bundle_specs: Dict[str, dict],
    column_mapping_by_table: Dict[str, Dict[str, str]],
    target_conn: Any,
    target_watermark: Dict[str, str],
    secret_key: bytes,
    public_key: bytes,
    output_root: Path,
    rng: Optional[random.Random] = None,
    receipt_predecessor_for_table: Optional[Dict[str, str]] = None,
) -> Optional[CDCEventQuarantineEntry]:
    """Replay a single ``ChangeEvent`` against ``target_conn``. Returns a
    quarantine entry if the event failed; ``None`` if it succeeded or was
    skipped as a re-delivery."""
    receipt_predecessor_for_table = receipt_predecessor_for_table or {}
    if event.op == "T":
        if "Truncate" not in state.unhandled_event_types:
            state.unhandled_event_types.append("Truncate")
        return CDCEventQuarantineEntry(
            migration_id=state.migration_id,
            event_lsn=event.lsn,
            relation_id=event.relation_id,
            table=event.table_name,
            op="T",
            failure_category="unmapped_column",
            failure_detail="Truncate not auto-replayed in PR C (PR D scope)",
            timestamp=_utcnow_iso(),
        )

    table = event.table_name
    if table not in column_mapping_by_table:
        return CDCEventQuarantineEntry(
            migration_id=state.migration_id,
            event_lsn=event.lsn,
            relation_id=event.relation_id,
            table=table,
            op=event.op,
            failure_category="unknown_relation",
            failure_detail=f"relation {table!r} not in D1 column mappings",
            timestamp=_utcnow_iso(),
        )

    def _quarantine(category: str, detail: str) -> CDCEventQuarantineEntry:
        return CDCEventQuarantineEntry(
            migration_id=state.migration_id,
            event_lsn=event.lsn,
            relation_id=event.relation_id,
            table=table,
            op=event.op,
            failure_category=category,
            failure_detail=detail,
            timestamp=_utcnow_iso(),
        )

    # Idempotency check — every prior event for this table sets
    # target_watermark[table]. pgoutput gives every change in a transaction
    # the same commit LSN, so the watermark is the (lsn, seq) pair: lsn
    # alone would drop rows 2..N of a multi-row transaction as
    # "re-deliveries".
    watermark = target_watermark.get(table)
    if watermark is not None and (
        (_hash_lsn(event.lsn), event.seq) <= _watermark_tuple(watermark)
    ):
        state.events_idempotent_skipped += 1
        return None

    transformer_hashes: List[str] = []

    def _xform(cols: Tuple[Tuple[str, Any], ...]):
        """Map + transform source columns into target space; quarantine entry on failure."""
        vals: List[Tuple[str, Any]] = []
        for col, val in cols:
            spec = bundle_specs.get(f"{table}.{col}")
            target_col = column_mapping_by_table[table].get(col, col)
            if spec is None:
                vals.append((target_col, val))
                continue
            try:
                result = execute(spec["python_source"], val, timeout_ms=4000)
            except _SecurityViolationError as exc:
                return _quarantine(
                    "transform_error", f"security_violation: {exc.violation.reason}"
                )
            if isinstance(result, ExecutionSuccess):
                vals.append((target_col, result.result_json))
                transformer_hashes.append(_hash(spec["python_source"]))
            else:
                return _quarantine("transform_error", repr(result))
        return vals

    # Data values: the after-image for I/U; deletes carry no new data.
    target_values: List[Tuple[str, Any]] = []
    if event.op in ("I", "U"):
        if event.after is None:
            return _quarantine("schema_drift", "event has neither before nor after tuple")
        xformed = _xform(event.after)
        if isinstance(xformed, CDCEventQuarantineEntry):
            return xformed
        target_values = xformed

    # Predicate values for U/D: replica-identity key columns when known,
    # else the full before-image. An update with no before-image and no
    # known key cannot be located safely on the target.
    predicate_values: List[Tuple[str, Any]] = []
    if event.op in ("U", "D"):
        pred_source = event.before if event.before is not None else event.after
        if pred_source is None:
            return _quarantine("schema_drift", "event has neither before nor after tuple")
        if event.key_columns:
            keyset = set(event.key_columns)
            pred_pairs = tuple((c, v) for c, v in pred_source if c in keyset)
        elif event.before is not None:
            pred_pairs = event.before
        else:
            return _quarantine(
                "schema_drift",
                "update without before-image or replica-identity key — "
                "cannot build a safe target predicate",
            )
        if not pred_pairs:
            return _quarantine("schema_drift", "empty predicate tuple for U/D event")
        xformed = _xform(pred_pairs)
        if isinstance(xformed, CDCEventQuarantineEntry):
            return xformed
        predicate_values = xformed

    # Write to target with op-correct parameterized SQL: INSERT for 'I',
    # UPDATE-by-predicate for 'U', DELETE-by-predicate for 'D'.
    try:
        cur = target_conn.cursor()
        tname = _qident(table)
        if event.op == "I":
            cols = [c for c, _ in target_values] + ["__omnix_cdc_lsn"]
            sql = (
                f"INSERT INTO {tname} ({', '.join(_qident(c) for c in cols)}) "
                f"VALUES ({', '.join(['%s'] * len(cols))})"
            )
            params = tuple(v for _, v in target_values) + (event.lsn,)
        elif event.op == "U":
            set_sql = ", ".join(
                f"{_qident(c)} = %s" for c, _ in target_values
            ) + f", {_qident('__omnix_cdc_lsn')} = %s"
            where_sql = " AND ".join(
                f"{_qident(c)} IS NOT DISTINCT FROM %s" for c, _ in predicate_values
            )
            sql = f"UPDATE {tname} SET {set_sql} WHERE {where_sql}"
            params = (
                tuple(v for _, v in target_values)
                + (event.lsn,)
                + tuple(v for _, v in predicate_values)
            )
        else:  # "D"
            where_sql = " AND ".join(
                f"{_qident(c)} IS NOT DISTINCT FROM %s" for c, _ in predicate_values
            )
            sql = f"DELETE FROM {tname} WHERE {where_sql}"
            params = tuple(v for _, v in predicate_values)
        cur.execute(sql, params)
        if hasattr(target_conn, "commit"):
            target_conn.commit()
    except Exception as exc:
        return _quarantine("target_connection_error", str(exc))

    # Only after the target commit do we advance the watermark.
    target_watermark[table] = f"{event.lsn}#{event.seq}"
    state.last_applied_lsn = event.lsn
    state.events_replayed += 1

    # Sampled CDCEventReceipt
    if cdc_event_receipt_emitter.should_emit(rng):
        pred = receipt_predecessor_for_table.get(table, "0" * 64)
        if len(pred) != 64 or any(c not in "0123456789abcdef" for c in pred):
            pred = "0" * 64
        receipt = CDCEventReceipt(
            migration_id=state.migration_id,
            event_lsn=event.lsn,
            relation_id=event.relation_id,
            table=table,
            op=event.op,
            predecessor_hash=pred,
            transformer_spec_hashes=tuple(transformer_hashes),
            applied_at_target_timestamp=_utcnow_iso(),
            legacy_to_target_lag_ms=0,
        )
        cdc_event_receipt_emitter.emit(
            receipt,
            secret_key=secret_key,
            public_key=public_key,
            output_root=output_root,
        )
        state.receipts_emitted += 1

    return None


def run_cdc_replay(
    *,
    events: Iterable[ChangeEvent],
    migration_id: str,
    bundle_specs: Dict[str, dict],
    column_mapping_by_table: Dict[str, Dict[str, str]],
    target_conn: Any,
    secret_key: bytes,
    public_key: bytes,
    output_root: Path,
    receipt_predecessor_for_table: Optional[Dict[str, str]] = None,
    rng: Optional[random.Random] = None,
    max_events: Optional[int] = None,
) -> CDCReplayState:
    """Drive ``events`` through replay; emit sampled receipts; quarantine
    failures. Returns a :class:`CDCReplayState` snapshot at end of stream."""
    state = CDCReplayState(migration_id=migration_id)
    target_watermark: Dict[str, str] = {}
    quarantine = CDCQuarantineLog(
        migration_id=migration_id,
        output_root=output_root,
        secret_key=secret_key,
        public_key=public_key,
    )
    for i, event in enumerate(events):
        if max_events is not None and i >= max_events:
            break
        quar = replay_one(
            event,
            state=state,
            bundle_specs=bundle_specs,
            column_mapping_by_table=column_mapping_by_table,
            target_conn=target_conn,
            target_watermark=target_watermark,
            secret_key=secret_key,
            public_key=public_key,
            output_root=output_root,
            rng=rng,
            receipt_predecessor_for_table=receipt_predecessor_for_table,
        )
        if quar is not None:
            state.events_quarantined += 1
            quarantine.record(quar)
    quarantine.flush()
    return state


__all__ = ["CDCReplayState", "replay_one", "run_cdc_replay"]
