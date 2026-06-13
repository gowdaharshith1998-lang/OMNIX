# D5 — Change Data Capture

> Strangler-Fig data plane: capture supported PostgreSQL change events from the
> D4 snapshot LSN onwards via logical replication, replay through the same
> `TransformerSpec`s, surface lag honestly, propose cutover when sustained
> parity is met.

## Status

D5 is present for PostgreSQL CDC. Oracle and MySQL adapters are intentionally
stubbed and must not be described as available until implemented and verified.

## Strangler-Fig phases

```
1. Snapshot + Bulk (D4)           — consistent legacy snapshot at LSN L0;
                                     bulk import via D3 transformers.
2. CDC start at L0 (D5)           — START_REPLICATION from L0; no gap.
3. Catch-up (D5)                  — process backlog accumulated during bulk;
                                     lag is expected to decrease as backlog drains.
4. Steady-state replay (D5)       — target stays within seconds of legacy.
5. Parity check (D5 lag monitor)  — sustained low lag + low divergence.
6. Cutover (operator)             — operator signs CutoverProposal; app
                                     traffic moves to target.
```

D5's job is phases 2–5. Phase 6 is operator-driven; D5 never auto-cuts.

## pgoutput binary protocol

D5 consumes the PG `pgoutput` plugin (built into PG 10+ and available on many
managed PostgreSQL services when logical replication is enabled). The parser
(`pg_adapter/pgoutput_parser.py`) handles:

| Tag | Meaning | Current behavior |
| --- | --- | --- |
| `R` | Relation schema | Cached by `relation_id`. |
| `B` | Begin transaction | Records final_lsn + commit_ts + xid. |
| `I` | Insert | Yields `ChangeEvent(op="I", after=tuple)`. |
| `U` | Update | Yields `ChangeEvent(op="U", before=key-or-full, after=new)`. |
| `D` | Delete | Yields `ChangeEvent(op="D", before=key-or-full)`. |
| `C` | Commit | Records end_lsn. |
| `T` | Truncate | Surfaces in `unhandled_event_types_seen` + quarantines; automatic replay is future work. |
| `M`/`Y`/`O`/`S` | Other | Counted in `unhandled_event_types_seen`. |

Tuple data kinds: `n` (NULL), `u` (TOAST-unchanged — surfaced as
`_UnchangedToast` sentinel; a later fetch path may resolve it), `t` (text repr),
`b` (binary). Truncated/corrupted bytes raise `ParseError` — **never
silently skipped**.

## Idempotency via `__omnix_cdc_lsn` watermark

Every target row written by the replayer carries `__omnix_cdc_lsn = <event
LSN>`. On re-delivery (the same LSN landing twice — a normal PG behaviour
after slot replay), the replayer compares the event's LSN against the
table's watermark and skips with `state.events_idempotent_skipped += 1`.

The watermark is **only advanced after the target write commits**. This is
the critical invariant: if a write fails, the LSN does not advance, the
event quarantines, and on next replay the same LSN arrives again — it does
not vanish.

## CDC event receipt sampling

Per-event signing can dominate high-throughput CDC workloads, so D5 samples at
`OMNIX_DM_CDC_EVENT_RECEIPT_SAMPLE_RATE` (default 0.01 = 1%).

**Each replayed event that reaches the target carries the `__omnix_cdc_lsn`
watermark.** Quarantined and unhandled events are reported separately. The
sampled receipts are for audit review. Set the rate to `1.0` for pilots that
need full audit detail and accept the throughput cost.

## Lag monitor + CutoverProposal

`LagMonitor.tick()` runs every `OMNIX_DM_LAG_REPORT_INTERVAL_SEC` (default
30s) and:

1. Queries legacy current LSN. If the query fails, sets
   `legacy_unreachable=True` and `lag_lsn_bytes=None` — **never silently
   reports 0 lag.**
2. Reads target's `__omnix_cdc_lsn` watermark. Same honest handling.
3. Computes `lag_lsn_bytes = legacy_lsn - target_lsn` (LSN integers).
4. Computes `lag_estimated_seconds = lag_lsn_bytes /
   bytes_per_second_estimate` (operator-tunable).
5. Builds a signed `LagReport`.

`CutoverState.evaluate(report)` runs a sustained-window state machine:

* If lag is finite and ≤ threshold AND every parity metric's
  `divergence_rate ≤ OMNIX_DM_CUTOVER_PARITY_THRESHOLD` AND the window has
  elapsed for ≥ `OMNIX_DM_CUTOVER_SUSTAINED_WINDOW_SEC` (default 15 min) →
  emit `CutoverProposal(recommended_action="operator_sign")`.
* If any parity metric exceeds threshold → emit
  `CutoverProposal(parity_not_met=True,
  recommended_action="investigate_divergence")`. **Honest — never silently
  propose cutover.**

`parity_metrics` is structural in the current D5 path (`divergence_rate=0.0`);
a later row-diff gate fills it with real divergence data.

## Replication slot lifecycle

Logical replication slots **block WAL recycling on the legacy DB**. If
OMNIX-DM crashes and leaves a slot orphaned, legacy fills its disk. D5
provides:

* `atexit` handler that tears down the slot on normal Python exit.
* SIGINT/SIGTERM handlers do the same.
* If teardown fails (legacy unreachable), the receipt records the abandoned
  slot for operator manual cleanup:

```sql
SELECT pg_drop_replication_slot('omnix_<migration_id>');
```

A later hardening phase will add periodic health-checked teardown with retry.

## Oracle + MySQL adapters

Oracle and MySQL CDC are out of scope for the current D5 implementation.
`OracleAdapter.start()` and `MySQLAdapter.start()` raise an explicit
`NotYetImplementedInPRC` error — **never a silent NOP**.

The planned adapter path is documented in the adapter module docstrings:
LogMiner via `cx_Oracle` for Oracle, `mysql-replication` for MySQL.

## Honest gaps deferred

* **Parity metrics divergence_rate** filled by a later row-diff gate.
* **Truncate auto-replay** in a later CDC phase; the current path quarantines.
* **Streaming-protocol messages** (StreamStart/StreamStop/StreamAbort/
  StreamCommit) counted as unhandled in the current path; a later phase adds full streaming
  support for very large in-progress transactions.
* **PG version matrix beyond 18.x** in a later compatibility pass.
