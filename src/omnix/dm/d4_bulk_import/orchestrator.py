"""Bulk-import orchestrator.

Glues reader → executor pool → target writer → batch-receipt emitter,
threading bounded queues for backpressure. Persists a resume cursor after
every batch so that an SIGINT'd or crashed run can rerun and pick up at
the next batch.

The orchestrator is connection-agnostic by design: callers pass
factory callables that yield a fresh connection (so the writer-thread can
recover from transient drops). Tests pass mocks; the operator runbook
shows the real psycopg2 invocation.
"""

from __future__ import annotations

import datetime
import hashlib
import signal
import time
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from omnix.crypto import ml_dsa_65
from omnix.dm._types import (
    BatchReceipt,
    BulkResult,
    ColumnSpec,
    Dialect,
    SchemaSpec,
)
from omnix.dm.d4_bulk_import._fk_topo import build_fk_topo_order
from omnix.dm.d4_bulk_import.batch_receipt_emitter import (
    db_fingerprint as _db_fingerprint,
    emit as emit_batch_receipt,
)
from omnix.dm.d4_bulk_import.checkpoint import (
    CheckpointState,
    TableCheckpoint,
    read_checkpoint,
    write_checkpoint,
)
from omnix.dm.d4_bulk_import.consumer import ConsumedBundle
from omnix.dm.d4_bulk_import.executor_pool import ExecutorPool
from omnix.dm.d4_bulk_import.legacy_reader import iter_batches
from omnix.dm.d4_bulk_import.quarantine import QuarantineLog
from omnix.dm.d4_bulk_import.target_writer import write_batch


@dataclass(frozen=True)
class TargetDBInfo:
    user: str
    host: str
    port: int
    database: str

    def fingerprint(self) -> str:
        return _db_fingerprint(self.user, self.host, self.port, self.database)


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def run_bulk_import(
    *,
    bundle: ConsumedBundle,
    legacy_conn: Any,
    target_conn: Any,
    legacy_dialect: Dialect,
    target_dialect: Dialect,
    target_db_info: TargetDBInfo,
    output_root: Path,
    secret_key: bytes,
    public_key: bytes,
    snapshot_lsn: Optional[str] = None,
    resume: bool = True,
    use_copy: bool = True,
    allow_deferred_cycles: bool = False,
    worker_count: int = 4,
    table_subset: Optional[Sequence[str]] = None,
) -> BulkResult:
    """Run the D4 bulk import end-to-end. Returns a :class:`BulkResult`."""
    output_root = Path(output_root)
    checkpoint_path = output_root / bundle.migration_id / "d4" / "checkpoint.json"

    topo = build_fk_topo_order(
        bundle.legacy_schema, allow_deferred_cycles=allow_deferred_cycles
    )
    deferred = set(topo.deferred_cycle)

    quarantine = QuarantineLog(
        migration_id=bundle.migration_id,
        output_root=output_root,
        secret_key=secret_key,
        public_key=public_key,
        phase="d4_bulk",
    )

    checkpoint = (
        read_checkpoint(checkpoint_path)
        if resume and checkpoint_path.exists()
        else None
    )
    if checkpoint is None:
        checkpoint = CheckpointState(migration_id=bundle.migration_id, tables={})

    tables_complete: List[str] = []
    tables_halted: List[str] = []
    unmapped = set(bundle.unmapped_columns)
    total_written = 0
    total_quarantined = 0
    interrupted = {"flag": False}

    def _handle_sigint(_sig, _frame):
        interrupted["flag"] = True

    prior_int = signal.getsignal(signal.SIGINT)
    prior_term = signal.getsignal(signal.SIGTERM)
    try:
        signal.signal(signal.SIGINT, _handle_sigint)
        signal.signal(signal.SIGTERM, _handle_sigint)
    except ValueError:
        # Signals can only be set in the main thread; in tests we may be off-thread.
        pass

    column_mapping_by_table: Dict[str, Dict[str, str]] = {}
    for m in bundle.column_mappings:
        column_mapping_by_table.setdefault(m.legacy_table, {})[m.legacy_column] = (
            m.target_column or m.legacy_column
        )

    spec_for_table: Dict[str, Dict[str, dict]] = {}
    for key, spec in bundle.transformer_specs.items():
        table, column = key.split(".", 1)
        spec_for_table.setdefault(table, {})[column] = spec

    halted_tables: set = set()

    with ExecutorPool(worker_count=worker_count) as pool:
        for table in topo.order:
            if interrupted["flag"]:
                break
            if table_subset is not None and table not in table_subset:
                continue
            if table not in column_mapping_by_table:
                # Column-mapping has no entries for this legacy table — skip.
                continue
            # Halt this table if any of its legacy columns mapped to a halt receipt.
            table_specs = spec_for_table.get(table, {})
            mapped_legacy_columns = set(column_mapping_by_table[table])
            table_unmapped = mapped_legacy_columns - set(table_specs.keys())
            if any(
                f"{table}.{col}" in bundle.transformer_halts
                for col in mapped_legacy_columns
            ):
                halted_tables.add(table)
                tables_halted.append(table)
                continue

            # Find ColumnSpec list for the reader.
            legacy_table_spec = next(
                (t for t in bundle.legacy_schema.tables if t.name == table), None
            )
            if legacy_table_spec is None:
                halted_tables.add(table)
                tables_halted.append(table)
                continue
            columns = list(legacy_table_spec.columns)
            pk_cols = legacy_table_spec.primary_key or tuple()

            resume_after = (
                checkpoint.tables[table].last_batch_no_complete
                if table in checkpoint.tables
                else -1
            )

            table_complete_ok = True
            transformer_spec_hashes = tuple(
                hashlib.sha256(spec["python_source"].encode("utf-8")).hexdigest()
                for spec in spec_for_table.get(table, {}).values()
            )

            for batch in iter_batches(
                table=table,
                columns=columns,
                dialect=legacy_dialect,
                conn=legacy_conn,
                migration_id=bundle.migration_id,
                snapshot_lsn=snapshot_lsn,
                pk_columns=pk_cols,
            ):
                if interrupted["flag"]:
                    table_complete_ok = False
                    break
                if batch.batch_no <= resume_after:
                    continue

                start = time.monotonic()
                ts_start = _utcnow_iso()
                transformed, quar_entries = pool.submit(
                    batch,
                    transformer_specs=table_specs,
                    column_mapping=column_mapping_by_table[table],
                )
                # Add any unmapped-column failures explicitly.
                for col in table_unmapped:
                    unmapped.add(f"{table}.{col}")

                write_result = write_batch(
                    transformed,
                    target_conn,
                    dialect=target_dialect,
                    use_copy=use_copy,
                    deferred_constraints=table in deferred,
                )
                quarantine.extend(quar_entries)
                quarantine.extend(write_result.quarantine_entries)
                ts_end = _utcnow_iso()
                elapsed = time.monotonic() - start

                rows_quar_total = len(quar_entries) + len(write_result.quarantine_entries)
                receipt = BatchReceipt(
                    migration_id=bundle.migration_id,
                    table=table,
                    batch_no=batch.batch_no,
                    batch_id=batch.batch_id,
                    predecessor_hash=bundle.predecessor_hash,
                    rows_read=len(batch.rows),
                    rows_written=write_result.rows_written,
                    rows_quarantined=rows_quar_total,
                    quarantine_offsets=tuple(transformed.quarantined_offsets)
                    + tuple(q.row_offset for q in write_result.quarantine_entries),
                    transformer_spec_hashes=transformer_spec_hashes,
                    target_db_fingerprint=target_db_info.fingerprint(),
                    timestamp_start=ts_start,
                    timestamp_end=ts_end,
                    elapsed_seconds=elapsed,
                )
                emit_batch_receipt(
                    receipt,
                    secret_key=secret_key,
                    public_key=public_key,
                    output_root=output_root,
                )
                total_written += receipt.rows_written
                total_quarantined += receipt.rows_quarantined

                # Update checkpoint after the receipt is durable.
                last_pk = (
                    batch.rows[-1].pk_value_repr if batch.rows else None
                )
                tc = checkpoint.tables.copy()
                tc[table] = TableCheckpoint(
                    table=table,
                    last_batch_no_complete=batch.batch_no,
                    last_pk_seen=last_pk,
                )
                checkpoint = CheckpointState(
                    migration_id=bundle.migration_id, tables=tc
                )
                write_checkpoint(checkpoint_path, checkpoint)

            if table_complete_ok and not interrupted["flag"]:
                tables_complete.append(table)
            else:
                tables_halted.append(table)

    # Restore signal handlers (if we replaced them)
    try:
        signal.signal(signal.SIGINT, prior_int)
        signal.signal(signal.SIGTERM, prior_term)
    except ValueError:
        pass

    quarantine.flush()

    phase = "halted" if interrupted["flag"] else "complete"
    if halted_tables:
        phase = "halted" if phase == "complete" else phase

    return BulkResult(
        migration_id=bundle.migration_id,
        phase=phase,
        tables_complete=tuple(tables_complete),
        tables_halted=tuple(tables_halted),
        unmapped_columns=tuple(sorted(unmapped)),
        total_rows_written=total_written,
        total_rows_quarantined=total_quarantined,
        partial=total_quarantined > 0 or bool(tables_halted) or interrupted["flag"],
        snapshot_lsn=snapshot_lsn,
    )


__all__ = ["TargetDBInfo", "run_bulk_import"]
