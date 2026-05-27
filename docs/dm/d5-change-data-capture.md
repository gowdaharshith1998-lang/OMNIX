# D5 — Change Data Capture (PR C)

> Strangler-Fig data plane: capture every legacy write from the D4 snapshot
> LSN onwards via PostgreSQL logical replication, replay through the same
> `TransformerSpec`s, surface lag honestly, propose cutover when sustained
> parity is met.

## Strangler-Fig phases

```
1. Snapshot + Bulk (D4)           — consistent legacy snapshot at LSN L0;
                                     bulk import via PR B transformers.
2. CDC start at L0 (D5)           — START_REPLICATION from L0; no gap.
3. Catch-up (D5)                  — process backlog accumulated during bulk;
                                     lag drops monotonically.
4. Steady-state replay (D5)       — target stays within seconds of legacy.
5. Parity check (D5 lag monitor)  — sustained low lag + low divergence.
6. Cutover (operator + PR F)      — operator signs CutoverProposal; app
                                     traffic moves to target.
```

D5's job is phases 2–5. Phase 6 is operator-driven; PR C never auto-cuts.

## pgoutput binary protocol

D5 consumes the PG `pgoutput` plugin (built into PG 10+, the default for
managed services like AWS RDS / Google Cloud SQL / Azure). The parser
(`pg_adapter/pgoutput_parser.py`) handles:

| Tag | Meaning | PR C behaviour |
| --- | --- | --- |
| `R` | Relation schema | Cached by `relation_id`. |
| `B` | Begin transaction | Records final_lsn + commit_ts + xid. |
| `I` | Insert | Yields `ChangeEvent(op="I", after=tuple)`. |
| `U` | Update | Yields `ChangeEvent(op="U", before=key-or-full, after=new)`. |
| `D` | Delete | Yields `ChangeEvent(op="D", before=key-or-full)`. |
| `C` | Commit | Records end_lsn. |
| `T` | Truncate | Surfaces in `unhandled_event_types_seen` + quarantines. PR D will auto-replay. |
| `M`/`Y`/`O`/`S` | Other | Counted in `unhandled_event_types_seen`. |

Tuple data kinds: `n` (NULL), `u` (TOAST-unchanged — surfaced as
`_UnchangedToast` sentinel; PR D may add a fetch path), `t` (text repr),
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

Emitting one ML-DSA-65-signed receipt per CDC event is infeasible at OLTP
scale (10K-100K events/sec; signing is ~5-10ms each). PR C samples at
`OMNIX_DM_CDC_EVENT_RECEIPT_SAMPLE_RATE` (default 0.01 = 1%).

**Every event is still individually replayed + landed on target with the
`__omnix_cdc_lsn` watermark.** The durable proof of replay is the target
row + watermark; the sampled receipts are for audit. Set the rate to `1.0`
for compliance pilots that need full audit and accept the throughput cost.

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

`parity_metrics` is structural in PR C (`divergence_rate=0.0`); PR D's
G7 row-diff gate fills it with real divergence data.

## Replication slot lifecycle

Logical replication slots **block WAL recycling on the legacy DB**. If
OMNIX-DM crashes and leaves a slot orphaned, legacy fills its disk. PR C
provides:

* `atexit` handler that tears down the slot on normal Python exit.
* SIGINT/SIGTERM handlers do the same.
* If teardown fails (legacy unreachable), the receipt records the abandoned
  slot for operator manual cleanup:

```sql
SELECT pg_drop_replication_slot('omnix_<migration_id>');
```

PR D will add periodic health-checked teardown with retry.

## Oracle + MySQL adapters

Both are stubbed in PR C. `OracleAdapter.start()` and `MySQLAdapter.start()`
raise `NotYetImplementedInPRC` with a message naming PR D. Any customer
attempting Oracle or MySQL CDC gets a clear error — **never a silent NOP**.

PR D's plan is documented in the adapter module docstrings: LogMiner via
`cx_Oracle` for Oracle, `mysql-replication` library for MySQL.

## Honest gaps deferred

* **Parity metrics divergence_rate** filled by PR D's G7 row-diff gate.
* **Truncate auto-replay** in PR D (PR C quarantines).
* **Streaming-protocol messages** (StreamStart/StreamStop/StreamAbort/
  StreamCommit) counted as unhandled in PR C; PR D adds full streaming
  support for very large in-progress transactions.
* **PG version matrix beyond 18.x** in PR D.
