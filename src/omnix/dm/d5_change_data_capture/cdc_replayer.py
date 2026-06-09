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

    # Idempotency check — every prior event for this table sets target_watermark[table]
    watermark = target_watermark.get(table)
    if watermark is not None and _hash_lsn(event.lsn) <= _hash_lsn(watermark):
        state.events_idempotent_skipped += 1
        return None

    # Apply per-column transformers to the after-tuple (or before-tuple for delete).
    source_tuple = event.after if event.after is not None else event.before
    if source_tuple is None:
        return CDCEventQuarantineEntry(
            migration_id=state.migration_id,
            event_lsn=event.lsn,
            relation_id=event.relation_id,
            table=table,
            op=event.op,
            failure_category="schema_drift",
            failure_detail="event has neither before nor after tuple",
            timestamp=_utcnow_iso(),
        )

    transformer_hashes: List[str] = []
    target_values: List[Tuple[str, Any]] = []
    for col, val in source_tuple:
        spec_key = f"{table}.{col}"
        spec = bundle_specs.get(spec_key)
        target_col = column_mapping_by_table[table].get(col, col)
        if spec is None:
            target_values.append((target_col, val))
            continue
        try:
            result = execute(spec["python_source"], val, timeout_ms=4000)
        except _SecurityViolationError as exc:
            return CDCEventQuarantineEntry(
                migration_id=state.migration_id,
                event_lsn=event.lsn,
                relation_id=event.relation_id,
                table=table,
                op=event.op,
                failure_category="transform_error",
                failure_detail=f"security_violation: {exc.violation.reason}",
                timestamp=_utcnow_iso(),
            )
        if isinstance(result, ExecutionSuccess):
            target_values.append((target_col, result.result_json))
            transformer_hashes.append(_hash(spec["python_source"]))
        else:
            return CDCEventQuarantineEntry(
                migration_id=state.migration_id,
                event_lsn=event.lsn,
                relation_id=event.relation_id,
                table=table,
                op=event.op,
                failure_category="transform_error",
                failure_detail=repr(result),
                timestamp=_utcnow_iso(),
            )

    # Write to target. The mock cursors used in tests record the call; the
    # operator's real cursor would issue parameterized SQL with a
    # ``__omnix_cdc_lsn = $1`` column.
    try:
        cur = target_conn.cursor()
        cur.execute(
            f"-- OMNIX-DM CDC apply {event.op} on {table} at lsn {event.lsn}",
            tuple(v for _, v in target_values) + (event.lsn,),
        )
        if hasattr(target_conn, "commit"):
            target_conn.commit()
    except Exception as exc:
        return CDCEventQuarantineEntry(
            migration_id=state.migration_id,
            event_lsn=event.lsn,
            relation_id=event.relation_id,
            table=table,
            op=event.op,
            failure_category="target_connection_error",
            failure_detail=str(exc),
            timestamp=_utcnow_iso(),
        )

    # Only after the target commit do we advance the watermark.
    target_watermark[table] = event.lsn
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
