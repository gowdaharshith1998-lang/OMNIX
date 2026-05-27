"""Transformer executor pool.

Wraps PR B's ``transformer_dsl.execute`` with concurrency. Each call to
``execute`` already spawns a fenced subprocess with ``RestrictedPython``
compile + ``resource.setrlimit`` (CPU=5s, AS=256MB, NOFILE=8). The pool
provides:

  * thread-based concurrency so we can have ``OMNIX_DM_BULK_WORKER_COUNT``
    in-flight transformer subprocesses at once,
  * per-batch dispatch that returns a ``TransformedBatch`` + a list of
    quarantined ``(row_offset, RowQuarantineEntry)`` for any failure,
  * security-violation propagation (the LLM-emitted source did something
    forbidden → the entire batch's failures are recorded with that
    category, so the orchestrator can HALT the table-level loop).

Worker-process recycle (P4 EARS bullet) is a no-op here because each call
already spawns a fresh subprocess. The "long-lived worker" optimisation
listed in the dispatch is a PR D performance concern; we ship the
security-correct baseline now.
"""

from __future__ import annotations

import concurrent.futures
import datetime
import hashlib
import os
from typing import Dict, List, Optional, Tuple

from omnix.dm._types import (
    Batch,
    RowQuarantineEntry,
    TransformedBatch,
    TransformedRow,
)
from omnix.dm.d3_transformation_synthesis.transformer_dsl import (
    ExecutionSuccess,
    _SecurityViolationError,
    execute,
)


def _utcnow_iso() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _hash_pk(pk_repr: str) -> str:
    return hashlib.sha256(pk_repr.encode("utf-8")).hexdigest()


def _hash_spec(source: str) -> str:
    return hashlib.sha256(source.encode("utf-8")).hexdigest()


class ExecutorPool:
    """Bounded thread pool dispatching per-(row, column) transformer calls.

    Each call goes through ``transformer_dsl.execute`` which itself spawns a
    fenced subprocess. The thread pool here is purely for IPC concurrency
    — the security boundary lives in PR B's subprocess.
    """

    def __init__(
        self,
        *,
        worker_count: Optional[int] = None,
        per_row_timeout_ms: int = 4000,
    ):
        self.worker_count = (
            worker_count
            if worker_count is not None
            else int(os.environ.get("OMNIX_DM_BULK_WORKER_COUNT", "4"))
        )
        self.per_row_timeout_ms = per_row_timeout_ms
        self._executor = concurrent.futures.ThreadPoolExecutor(
            max_workers=self.worker_count
        )
        self._closed = False

    def close(self) -> None:
        if not self._closed:
            self._executor.shutdown(wait=True, cancel_futures=False)
            self._closed = True

    def __enter__(self):  # context-manager friendly
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()

    # ------------------------------------------------------------------

    def submit(
        self,
        batch: Batch,
        *,
        transformer_specs: Dict[str, dict],
        column_mapping: Dict[str, str],
    ) -> Tuple[TransformedBatch, List[RowQuarantineEntry]]:
        """Run ``batch`` through the per-column transformers.

        ``transformer_specs`` is a dict ``{legacy_column → spec_payload}`` where
        spec_payload has at least ``"python_source"``. ``column_mapping`` maps
        ``legacy_column → target_column`` (from D1).

        Returns ``(TransformedBatch, quarantine_entries)``. The transformed
        batch's ``transformed_rows`` excludes rows whose offset is in
        ``quarantined_offsets``.
        """
        if self._closed:
            raise RuntimeError("ExecutorPool is closed")

        transformed: List[TransformedRow] = []
        quarantine: List[RowQuarantineEntry] = []
        quarantined_offsets: List[int] = []

        # We process rows sequentially but each row's columns can be evaluated
        # in parallel via the thread pool. For tiny columns this is overkill,
        # but it gives good headroom for slow transformers (regex/decimal).
        for offset, row in enumerate(batch.rows):
            future_for_col: Dict[str, concurrent.futures.Future] = {}
            for col_name, value in row.column_values:
                spec = transformer_specs.get(col_name)
                if spec is None:
                    continue
                source = spec["python_source"]
                future_for_col[col_name] = self._executor.submit(
                    _safe_execute, source, value, self.per_row_timeout_ms
                )
            if not future_for_col:
                # No transformers for any column — pass row through unchanged
                # with target column names mapped via column_mapping.
                mapped = tuple(
                    (column_mapping.get(c, c), v) for c, v in row.column_values
                )
                transformed.append(
                    TransformedRow(
                        legacy_pk_value_repr=row.pk_value_repr,
                        target_column_values=mapped,
                    )
                )
                continue

            mapped_values: List[Tuple[str, object]] = []
            row_failed = False
            failure_category = ""
            failure_detail = ""
            failed_col_source_hash: Optional[str] = None
            # Carry-through unmapped columns verbatim
            unmapped = {c: v for c, v in row.column_values if c not in future_for_col}
            for col_name, value in row.column_values:
                if col_name not in future_for_col:
                    target_col = column_mapping.get(col_name, col_name)
                    mapped_values.append((target_col, value))
                    continue
                try:
                    result = future_for_col[col_name].result()
                except _SecurityViolationError as exc:
                    row_failed = True
                    failure_category = "security_violation"
                    failure_detail = exc.violation.reason
                    failed_col_source_hash = _hash_spec(
                        transformer_specs[col_name]["python_source"]
                    )
                    break
                except Exception as exc:  # noqa: BLE001
                    row_failed = True
                    failure_category = "transform_error"
                    failure_detail = f"{type(exc).__name__}: {exc}"
                    failed_col_source_hash = _hash_spec(
                        transformer_specs[col_name]["python_source"]
                    )
                    break
                if isinstance(result, ExecutionSuccess):
                    target_col = column_mapping.get(col_name, col_name)
                    mapped_values.append((target_col, result.result_json))
                else:
                    row_failed = True
                    failure_category = _category_from_result(result)
                    failure_detail = repr(result)
                    failed_col_source_hash = _hash_spec(
                        transformer_specs[col_name]["python_source"]
                    )
                    break

            if row_failed:
                quarantined_offsets.append(offset)
                quarantine.append(
                    RowQuarantineEntry(
                        migration_id=batch.migration_id,
                        batch_id=batch.batch_id,
                        row_offset=offset,
                        legacy_table=batch.table,
                        legacy_pk_value_hash=_hash_pk(row.pk_value_repr),
                        failure_category=failure_category,
                        failure_detail=failure_detail,
                        transformer_spec_hash=failed_col_source_hash,
                        retry_count=0,
                        timestamp=_utcnow_iso(),
                    )
                )
            else:
                transformed.append(
                    TransformedRow(
                        legacy_pk_value_repr=row.pk_value_repr,
                        target_column_values=tuple(mapped_values),
                    )
                )

        return (
            TransformedBatch(
                migration_id=batch.migration_id,
                table=batch.table,
                batch_no=batch.batch_no,
                batch_id=batch.batch_id,
                transformed_rows=tuple(transformed),
                quarantined_offsets=tuple(quarantined_offsets),
            ),
            quarantine,
        )


def _safe_execute(source: str, value, timeout_ms: int):
    """Wrapper so a SecurityViolation from compile_safe propagates as the
    typed exception (the thread pool would otherwise wrap it)."""
    return execute(source, value, timeout_ms=timeout_ms)


def _category_from_result(result) -> str:
    from omnix.dm._types import ExecutionError, ExecutionOOM, ExecutionTimeout

    if isinstance(result, ExecutionTimeout):
        return "transform_timeout"
    if isinstance(result, ExecutionOOM):
        return "transform_oom"
    if isinstance(result, ExecutionError):
        return "transform_error"
    return "transform_error"


__all__ = ["ExecutorPool"]
