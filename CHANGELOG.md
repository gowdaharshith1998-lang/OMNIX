# Changelog

All notable changes to OMNIX are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

#### OMNIX-DM data-migration layer (D1–D5)

The data-migration arm beneath the code replicator. AI proposes, deterministic
gates dispose: every stage emits signed, inspectable artifacts rather than a
claim of proven correctness. Grounded in the Wang/Dillig (UT Austin) research
trilogy — Mediator (POPL 2018), Migrator (arXiv 1904.05498), and Dynamite
(PVLDB 2020) — and the Strangler Fig migration pattern (Fowler, 2004).

- **D1 — schema understanding** (`omnix.dm.d1_schema_understanding`):
  dialect-aware DDL parsing for PostgreSQL, MySQL, Oracle (`NUMBER(p,s)`
  precision/scale and Oracle `DATE` timezone handling), and MongoDB
  (`$jsonSchema` with nested dotpaths). Per-column metadata extraction with
  read-only connection verification, and a Hungarian-optimal column matcher
  (`scipy.optimize.linear_sum_assignment`) with configurable confidence
  thresholds and top-3 candidate surfacing. Output: a signed
  `column-mapping.json`.
- **D2 — edge-case profiling** (`omnix.dm.d2_edge_case_profiling`): a
  budget-bounded probe planner driving six probers — null distribution, encoding
  anomaly (mojibake / non-UTF-8), orphan foreign key, timezone drift, precision
  boundary, and sentinel value. All probes use parameterized SQL with strict
  identifier and literal quoting. Output: a signed `edge-case-manifest.json`,
  cryptographically chained to D1.
- **D3 — transformation synthesis** (`omnix.dm.d3_transformation_synthesis`):
  per-column transformers (Python lambda, SQL `CASE`, or Datalog rule) verified
  by Hypothesis property tests derived from D2's blocker manifest. Uses a CEGIS
  sketch library and a critique loop bounded to five iterations, each grounded in
  a concrete minimal failing input. Columns that cannot be synthesized produce an
  explicit `HaltReport` rather than a silent identity fallback. Candidate code
  runs under a RestrictedPython AST allowlist inside a resource-limited
  subprocess fence.
- **D4 — bulk import** (`omnix.dm.d4_bulk_import`): streams every legacy row
  through the per-column transformers, batch-writes to the target via PostgreSQL
  `COPY FROM STDIN` or parameterized `INSERT`, and quarantines failures. Enforces
  a row-conservation invariant (`rows_read == rows_written + rows_quarantined`),
  foreign-key topological ordering (Kahn's algorithm with explicit cycle
  detection), and crash-safe resume via per-table checkpoints. Re-running a
  completed migration is a no-op.
- **D5 — change data capture** (`omnix.dm.d5_change_data_capture`): after the
  bulk load, captures ongoing legacy writes via PostgreSQL logical replication
  (`pgoutput`), replays each change through the same transformer specs, tracks
  lag, and emits a signed cutover proposal once statistical parity is sustained.
  Cutover is never auto-actioned — it requires an operator signature. Oracle
  (LogMiner) and MySQL (binlog) adapters are present as explicit stubs that fail
  loudly rather than silently no-op.

#### Provenance and cryptography

- **ML-DSA-65 (FIPS 204) signing infrastructure** (`omnix.crypto.ml_dsa_65`),
  a thin wrapper over `dilithium-py` (public key 1952 B, secret key 4032 B,
  signature 3309 B). Schema validation runs *before* signing, and every artifact
  is written atomically (temp file → fsync → `os.replace`).
- **Merkle-chained receipts** across the data-migration stages: each manifest's
  canonical SHA-256 becomes the next manifest's `predecessor_hash`, producing a
  tamper-evident audit trail that a third party can verify entirely offline.

#### Dependency hardening

- Replaced two unmaintained third-party dependencies with auditable, in-house,
  zero-dependency implementations: a pure-Python `pgoutput` binary parser
  (in place of the `pypgoutput` prototype) and a pure-Python stratified Datalog
  evaluator with negation-as-failure and aggregates (in place of `pyDatalog`).
  Both are Python 3.14 compatible.

### Notes

- New runtime dependency: `psycopg2-binary>=2.9.10,<3.0`.
- Live Oracle/PostgreSQL integration tests are opt-in and skipped by default
  (set `OMNIX_DM_RUN_INTEGRATION=1` to enable).
- The end-to-end formal-equivalence proof layer (Z3-discharged bisimulation) is
  deliberately out of scope for these stages and tracked for a future milestone;
  the receipts reserve the slot for it rather than implying it already exists.

## [0.6.1] - 2026-05-17

### Changed

- Consolidated the LLM tool-dispatch sources under the `omnix.*` namespace so
  they sit alongside the rest of the package tree. The public CLI is unchanged.
- Renamed the internal `omnix.axiom` Python module to `omnix.receipts`, naming it
  for what it does — emit and verify signed receipts — rather than for a product
  surface. The user-facing CLI verbs (`omnix axiom keygen`,
  `omnix axiom verify-scan`, `omnix axiom export-vault`) are unchanged; only the
  internal Python module path moved.

### Added

- A `tests/_blocked/` convention for tests that cannot yet run, each documented
  with a sibling `.WHY.md` recording the root cause and a restore checklist, and
  excluded from collection via `norecursedirs` in `pyproject.toml`.
- Spec-driven `xfail` markers on tests that assert not-yet-built interfaces, each
  naming the exact missing symbol so the gap stays explicit rather than hidden.

## [0.6.0] - 2026-05-16

### Changed

- **Namespace restructure:** all OMNIX source modules now live under the
  `omnix.*` namespace package (`src/omnix/`). The public CLI surface
  (`omnix analyze`, `omnix grammar`, `omnix find-bugs`, `omnix verify`) is
  unchanged; the repo-root `omnix.py` shim keeps both script invocation and
  `import omnix` stable for external integrators.
- Reconciled the `pyproject.toml` version metadata with the canonical project
  version, which had drifted since the first commit.

### Fixed

- **Turboscan environment propagation through `forkserver`:** on Python 3.14+
  the worker pool snapshots `os.environ` at first use, so per-codebase
  `OMNIX_FS_HYGIENE_*` configuration was stripped at the worker boundary. The fix
  threads hygiene configuration explicitly through the worker arguments, and
  clears stale keys when hygiene is disabled so a later scan cannot inherit an
  earlier scan's settings.
- **`omnix grammar list` off-by-one:** the language label stripped one character
  beyond the `tree_sitter_` prefix, printing e.g. `ava` instead of `java` for
  every grammar. It now strips exactly the prefix length.
