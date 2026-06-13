# D4 — Exhaustive Bulk Import

> Pipeline walkthrough, quarantine flow, idempotency contract, FK ordering
> rules, and the `__omnix_batch_id` DDL precondition.

## Status

D4 is present in the current tree as an operator-run bulk import phase. It
requires target DDL preconditions and should be verified in the customer's
database environment before use.

## What D4 delivers

For configured legacy tables in FK-safe topological order, D4 streams source rows
through D3 per-column `TransformerSpec`s, batch-writes the result to
target, and emits one ML-DSA-65 signed `BatchReceipt` per (table, batch_no)
with the same `predecessor_hash` (canonical SHA-256 of D2's
`edge-case-manifest.json`). Per-row failures land in a signed
`QuarantineManifest` with mode 0600.

## Operator DDL precondition

Before D4 runs, the operator MUST add a bookkeeping column to every migrated
target table:

```sql
ALTER TABLE owners ADD COLUMN __omnix_batch_id TEXT;
CREATE INDEX ON owners(__omnix_batch_id) WHERE __omnix_batch_id IS NOT NULL;
```

A later cleanup script drops this column post-cutover.

D4 enforces this precondition: if the column is missing, the target writer
raises `TargetSchemaError` instead of silently writing rows without
provenance.

## Pipeline

```
legacy DB ── server-side cursor ──> legacy_reader.iter_batches
                                          │
                                          ▼ Batch
                                   executor_pool.submit
                                  (D3 sandbox per row)
                                          │
                                          ▼ TransformedBatch + quarantine
                                    target_writer.write_batch
                                  (COPY-in or batched INSERT)
                                          │
                                          ▼
                                  batch_receipt_emitter.emit
                                          │
                                          ▼ atomic write
                                  checkpoint.write_checkpoint
```

## Row conservation invariant

For every emitted `BatchReceipt`:

```
rows_read == rows_written + rows_quarantined
```

This is enforced by a property test in
`tests/dm/property/test_d4_d5_invariants.py::test_row_conservation_across_a_synthetic_migration`.
It is the core invariant of D4 — every row that enters D4 either becomes
a row in target OR a quarantine entry. **No row vanishes silently.**

## Idempotency

`batch_id = sha256(migration_id || '|' || table || '|' || batch_no)`. The
target row carries `__omnix_batch_id = $batch_id`. Re-running the same
`migration_id`:

* Reader re-yields all source batches.
* Orchestrator's `resume=True` (default) reads `checkpoint.json` and skips
  every batch with `batch_no <= last_batch_no_complete`.
* If the operator wants to force a re-write of a specific batch, they delete
  the target rows with that batch_id and clear the checkpoint entry for that
  table.

## FK topological order

`_fk_topo.build_fk_topo_order` runs Kahn's algorithm over the FK graph from
D1's `SchemaSpec`. Self-references are tolerated (surfaced via
`DeferredConstraintWarning`); cross-table cycles raise `CycleInFKGraphError`
unless `allow_deferred_cycles=True` (which switches the orchestrator into
`SET CONSTRAINTS ALL DEFERRED` mode for the affected tables on PG).

## Quarantine flow

A row enters quarantine when any of:

* The transformer raises (`ExecutionError`) — including the `transform()`
  function itself raising, or a sandbox-detected security violation.
* The transformer times out (`ExecutionTimeout` — subprocess `SIGXCPU`).
* The transformer OOMs (`ExecutionOOM` — `RLIMIT_AS` triggers `SIGKILL`).
* Target write raises a constraint violation (unique/FK/NOT NULL/check) —
  isolated per row; siblings continue.
* Target write fails for a non-constraint reason after retry exhaustion
  (`OMNIX_DM_BULK_RETRY_MAX` default 3) — the row quarantines as
  `target_connection_error`.

The `QuarantineLog` writes a single signed manifest per migration (`d4_bulk`
phase). File mode is `0600`. Raw row values are **omitted** unless the
operator sets `OMNIX_DM_QUARANTINE_INCLUDE_VALUES=1` (pilots that need full
forensic data and accept the sensitive-data exposure). A later hardening phase
adds per-tenant key wrapping.

## Predecessor hash chain

Every `BatchReceipt.predecessor_hash` equals canonical SHA-256 of D2's
`edge-case-manifest.json`. All D4 batches for a migration share the same
predecessor — they fan out by `(table, batch_no)`. The chain integrity is
verified by:

```python
assert payload["predecessor_hash"] == bundle.predecessor_hash
```

in every integration + property test.

## Honest gaps deferred

* **No parallel COPY streams per table.** A later performance phase should add
  this following established bulk-load guidance. D4 currently documents
  single-stream COPY plus a multi-worker per-row transform pool.
* **No long-lived sandbox worker pool.** Each `execute()` call spawns a
  fresh subprocess (D3 kernel). A later phase will add a long-lived worker pool
  with per-job CPU reset via `SIGALRM` for higher throughput.
* **No live PG bulk-load tuning.** Operator runbook documents
  `max_wal_size` / `checkpoint_timeout` recommendations; a later phase may add an
  automated wizard.
