# Changelog

All notable changes to OMNIX are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added — OMNIX-DM PR C (D4 Bulk Import + D5 Change Data Capture)

- **`omnix.dm.d4_bulk_import` package** — the application layer that consumes
  PR B's signed `TransformerSpec` receipts and runs them at production scale.
  Streams every row from legacy through per-column transformers in a fenced
  subprocess pool (reuses PR B's RestrictedPython kernel verbatim — no new
  code-execution attack surface), batch-writes to target via PG `COPY FROM
  STDIN` or parameterized INSERT, captures every failure into a signed
  quarantine manifest, emits one ML-DSA-65 signed `BatchReceipt` per
  (table, batch_no), and persists a `checkpoint.json` so the operator can
  resume after any crash. **Row conservation invariant** enforced by
  property test: `rows_read == rows_written + rows_quarantined` per batch
  — never silently drops a row.
- **Per-dialect streaming legacy readers** for PostgreSQL (server-side
  named cursor with `itersize`), MySQL (SSCursor), Oracle (`arraysize`),
  and MongoDB (`find(batch_size=...)`). Memory-bounded regardless of source
  size. Transient errors retry with reconnect; permanent errors surface as
  `LegacyReadError` after retry exhaustion.
- **FK topological order** via Kahn's algorithm with explicit
  `CycleInFKGraphError`. Self-referential tables surface a
  `DeferredConstraintWarning`; cross-table cycles require
  `allow_deferred_cycles=True` and `SET CONSTRAINTS ALL DEFERRED` (PG).
- **Idempotency contract**: `batch_id = sha256(migration_id || table ||
  batch_no)` plus operator-supplied `__omnix_batch_id` column. Rerunning the
  same `migration_id` is a no-op; rerun-after-crash resumes from the
  per-table checkpoint.
- **`omnix.dm.d5_change_data_capture` package** — Strangler-Fig data plane.
  After D4 bulk completes from snapshot LSN `L0`, D5 captures every legacy
  write from `L0` onwards via PostgreSQL logical replication (`pgoutput`
  plugin), replays each event through the same `TransformerSpec` against
  target, tracks lag, and emits a signed `CutoverProposal` when statistical
  parity is sustained for `OMNIX_DM_CUTOVER_SUSTAINED_WINDOW_SEC` (default
  15 min). The proposal is **never auto-actioned** — the operator signs;
  PR F adds the signoff workflow.
- **Pure-Python `pgoutput` binary parser** (~400 LOC) — replaces unmaintained
  `pypgoutput` 2022 prototype. Parses Relation/Begin/Insert/Update/Delete/
  Commit/Truncate messages, decodes 11 common PG OIDs to native Python types
  (Decimal for NUMERIC, datetime+tzinfo for timestamptz, bytes for bytea),
  handles all 4 tuple kinds (n/u/t/b including TOAST-unchanged sentinel).
  Same pattern as PR B's pure-Python Datalog evaluator: replace unmaintained
  prototype with auditable in-house code.
- **Standby Status Update protocol** + heartbeat thread for slot
  `confirmed_flush_lsn` advancement.
- **Sampled `CDCEventReceipt` emission** at
  `OMNIX_DM_CDC_EVENT_RECEIPT_SAMPLE_RATE` (default 1%) — every event still
  lands on target + LSN watermark; sampled receipts are for audit. Set rate
  to `1.0` for compliance pilots that need full receipt.
- **Lag monitor with sustained-window state machine** + honest
  `legacy_unreachable=True` when the legacy health-check fails (never
  silently report 0 lag).
- **Oracle (LogMiner) + MySQL (binlog) CDC adapter stubs** that raise
  `NotYetImplementedInPRC` on `start()` with a message naming PR D as the
  implementer. Codex honesty — never silently NOP.
- **7 new Codex honesty surfaces**: `BulkResult.partial`,
  `BulkResult.unmapped_columns`, `RowQuarantineEntry`,
  `CDCResult.unhandled_event_types_seen`, `CDCEventQuarantineEntry`,
  `LagReport.legacy_unreachable`, `CutoverProposal.parity_not_met` +
  `recommended_action="investigate_divergence"`.
- **5 new schema constants** (append-only): `BATCH_RECEIPT_SCHEMA`,
  `QUARANTINE_MANIFEST_SCHEMA`, `CDC_EVENT_RECEIPT_SCHEMA`,
  `LAG_REPORT_SCHEMA`, `CUTOVER_PROPOSAL_SCHEMA`.
- **`psycopg2-binary>=2.9.10,<3.0`** runtime dep (verified 2.9.12 on Fedora 44).
- **Tests**: +130 new (21 P1/P2 · 11 reader · 8 executor pool · 12 target
  writer · 13 orchestrator + checkpoint · 16 quarantine + receipt emitter ·
  9 D5 core/stubs · 27 pgoutput parser · 6 standby status · 6 PG connection ·
  4 CDC quarantine · 12 CDC replayer · 6 lag monitor · 6 cutover proposal ·
  5 integration · 5 invariants).

Built on Migrator stage 3 (arXiv 1904.05498, Wang/Dillig); Strangler Fig
(Fowler 2004 / AWS Prescriptive / Azure Architecture Center); TSB Bank 2018
outage as cautionary anti-pattern (validation phase used a calendar exit
criterion); EY 2025 banking modernisation data (parallel-run extensions of
12-24 months when calendar exit criteria are used); LegacyLeap "Zero-Downtime
Migration" April 2026; PostgreSQL 18.4 logical replication / pgoutput plugin
docs (May 2026); AWS DMS + Google Cloud DMS bulk-to-CDC handoff semantics.

### Added — OMNIX-DM PR B (D3 AI Transformation Synthesis)

- **`omnix.dm.d3_transformation_synthesis` package** — the AI proposal layer
  that emits per-column transformers (Python lambda / SQL CASE / Datalog rule)
  verified by Hypothesis property tests derived from D2's blocker manifest.
  Built on Migrator (arXiv 1904.05498, Wang/Dillig) CEGIS with minimum-failing-input
  pruning, Reflexion (Shinn et al., NeurIPS 2023) restructured to ground
  every critique in concrete MFI rather than LLM self-judgment (Huang ICLR
  2024 trap explicitly avoided), and Property-Generated Solver (arXiv
  2506.18315) anchoring of test population in the immutable D2 blocker set
  to prevent BACE-style drift.
- **RestrictedPython 8.1 AST-rewriting sandbox** — the CVE-2026-40217
  (LiteLLM, May 2026) fix path. Strict allowlist of AST nodes + builtins +
  module attributes (NOT denylist), plus subprocess fence with
  `resource.setrlimit` (CPU=5s, AS=256MB, NOFILE=8). 10+ known CTF escape
  patterns pen-tested in `tests/dm/unit/d3/test_transformer_dsl.py`.
- **Grounded Reflexion loop** — max 5 iterations, MFI monotone (append-only),
  security halt immediate (never retried), no silent identity fallback.
  HaltReport receipts for un-synthesizable columns surface the failure mode
  + every MFI + the last critique for operator adjudication.
- **Migrator CEGIS with 15-sketch SketchLibrary** — covers the Petclinic
  surface (DATE→TIMESTAMP_TZ midnight UTC, decimal precision clamp, sentinel
  to NULL, mojibake normalize, email/phone/UUID format normalize, int
  widening/narrowing, bool from int/text, JSON encode/decode, binary
  passthrough, etc.). Pruned sketches recorded in receipt so future
  migrations learn from prior failures.
- **Pure-Python semi-naïve Datalog evaluator** (~250 LOC) — replaces
  unmaintained pyDatalog. Stratified Datalog with negation-as-failure,
  arithmetic + comparison built-ins, aggregates (count/sum/min/max),
  cycle/stratification detection at rule-load time. Python 3.14
  compatible. Zero external deps.
- **TransformerSpec + HaltReport receipts** — ML-DSA-65 signed, schema
  validated, atomically written. Every receipt's `predecessor_hash` is the
  canonical SHA-256 of D2's edge-case-manifest, building the cross-layer
  Merkle root PR F will finalize. `bisimulation_placeholder` reserves the
  slot PR E's Z3 TRA proof will fill (Cheung UC Berkeley EECS-2025-174 —
  bounded proofs feasible).
- **Auto-Hypothesis property generator** — per-type strategies (INTEGER /
  DECIMAL(p,s) / DATE / TIMESTAMP_TZ / STRING / BOOLEAN / JSON / BYTES) +
  per-blocker augmentation (mojibake → KNOWN_MOJIBAKE samples; sentinel →
  KNOWN_SENTINELS; timezone drift → MIDNIGHT_UTC_SAMPLES; precision boundary
  → DECIMAL boundary values). `StrategyUnavailable` halt for unmapped types
  — Codex honesty (never silently skip coverage).
- **Anthropic SDK ≥0.40 (anthropic 0.85.0 verified)** — Claude API wrapper
  with mockable backend (`OMNIX_DM_DISABLE_LLM=1` for CI default). Prompt-
  injection containment via `json.dumps` of all sample values; system prompt
  caching for 90% cost savings on per-column synthesis. 3-retry exponential
  backoff on rate limits.
- **Tests**: +124 new (32 sandbox + AST · 14 Datalog · 10 synthesizer · 15
  property generator · 10 Reflexion loop · 8 CEGIS · 6 SQL tier · 6 Datalog
  tier · 8 spec emitter · 6 halt report · 4 consumer · 1 integration · 5
  invariants). Total ~1236 passing. Pre-existing unrelated turboscan
  failure carries; not new.

### Added — OMNIX-DM PR A (D1 + D2)

- **`omnix.dm` package** — first 2 phases of the autonomous AI data migration
  platform that sits beneath OMNIX's code replicator. Built on the Wang/Dillig
  UT Austin trilogy (Mediator POPL 2018 / Migrator arXiv 1904.05498 / Dynamite
  PVLDB 2020) as the academic foundation. AI proposes, deterministic gates
  dispose. Every silent-drop path was rewritten to surface the gap honestly
  (Codex axiom).
- **D1 AI Schema Understanding** — dialect-aware DDL parsing for Postgres,
  MySQL, Oracle (NUMBER(p,s) precision/scale + Oracle DATE TZ-strip flag), and
  MongoDB (`$jsonSchema` with nested dotpaths). Per-column metadata extraction
  with read-only DB connection verification (PG `transaction_read_only`, MySQL
  `@@read_only`, Oracle `V$DATABASE.OPEN_MODE`). Read-only `codebase_memory`
  bridge that surfaces "graph not deployed" honestly instead of returning
  empty. `sentence-transformers/all-MiniLM-L6-v2` 384-dim embedder with
  deterministic-hash fallback for offline CI. Hungarian-optimal matcher
  (`scipy.optimize.linear_sum_assignment`) with `0.85` / `0.60` confidence
  thresholds and top-3 candidate surfacing. `OMNIX_DM_CONFIDENCE_THRESHOLD`
  env override.
- **D2 AI Edge-Case Profiling** — expected-free-energy probe planner
  (Friston FEP / pymdp-style; deterministic given seed; budget-enforced). Six
  probers: NULL distribution, encoding anomaly (mojibake / non-UTF8),
  orphan FK, timezone drift (incl. midnight clustering), precision boundary,
  sentinel value. All probers use parameterized SQL via `quote_ident()` which
  rejects any quote char in input. Sentinel literals go through
  `_safe_literal()` which rejects single-quote/newline/null.
- **ML-DSA-65 (FIPS 204) signing infrastructure** — `omnix.crypto.ml_dsa_65`
  thin wrapper over `dilithium-py` (verified: pk=1952, sk=4032, sig=3309
  bytes, OID `2.16.840.1.101.3.4.3.18`). Sign-then-emit-both atomic write
  pattern (temp file + `fsync` + `os.replace`). JSON Schema validation runs
  *before* signing so malformed payloads never get signed.
- **Merkle chain receipts** — every manifest's canonical SHA-256 becomes the
  next manifest's `predecessor_hash`. D2's edge-case-manifest is hard-required
  to chain to D1's column-mapping.
- **Tests**: 78 new tests across `tests/dm/` covering unit (parsers,
  metadata, embedder, matcher, emitters, signer, Merkle, 6 probers),
  property-based (Hypothesis: no legacy column silently dropped invariant),
  and an offline integration smoke test for the Oracle→PG Petclinic corpus.
  Full suite goes 1034 → 1112 passing (the 1 remaining failure is a
  pre-existing turboscan flake, orthogonal to this PR).
- **Docs**: `docs/dm/README.md`, `docs/dm/d1-schema-understanding.md`,
  `docs/dm/d2-edge-case-profiling.md`, `docs/dm/academic-foundation.md`.
- **pytest marker**: `integration_dm` (opt-in; skip unless
  `OMNIX_DM_RUN_INTEGRATION=1`).

### Honest gaps (deliberately scoped out of PR A)
- **`omnix.codebase_memory`** module is not yet deployed in this repo — the
  bridge surfaces this rather than guessing.
- **Live Oracle / Postgres integration tests** are skip-by-default; bringing
  up testcontainers is PR B's onboarding step.
- The "100-200% perfect migration" claim is not discharged by PR A. The
  formal proof layer (Z3-discharged bisimulation over TRA) lands in PR E.

## [0.6.1] - 2026-05-17

### Changed
- **Slice 15.3.7 LLM tool-dispatch source landed in `omnix.*` namespace (slice 21.8 / M0.5):** the WIP from stash `wip-slice-15.3.7-and-misc-post-PR` was applied onto a new branch off main, file-moved into the namespaced tree (`src/fabric/dispatch_tools.py` → `src/omnix/fabric/dispatch_tools.py`; `src/providers/tools/` → `src/omnix/providers/tools/`; 18 React/TS files under `src/studio/frontend/src/` merged into the existing `src/omnix/studio/frontend/src/` tree), and every `from src.X` / bare `from fabric|providers` import (plus the inline `monkeypatch.setattr("src.X...")` / `@mock.patch("fabric...")` string paths) retargeted to `from omnix.X`. Collision survey at `/tmp/slice-15.3.7-collision-manifest.md` confirmed 0 IDENTICAL, 0 COLLISION, 30 NEW — clean merge with no manual escalation.
- **`omnix.axiom` Python module renamed to `omnix.receipts` (M0 leftover folded into M0.5):** the module that emits and verifies signed receipts is now named for what it does, not for the marketing surface. 17 tracked files renamed via `git mv` (history preserved); 38 source files updated to import from `omnix.receipts` (every `omnix.axiom` dot-path reference + the two hardcoded internal-tree filesystem paths in `walker.py`'s pathological-skip list and `test_loader.py`'s ENCODING constant). **The user-facing CLI verb tree is unchanged** — `omnix axiom keygen`, `omnix axiom verify-scan`, and `omnix axiom export-vault` all still work; only the internal Python module path moved. The audit-export.zip shipped to early users continues to reference the `omnix axiom` verbs verbatim. Sibling-repo `apps/backend/src/omnix/axiom` references in `src/web/graph_data_axiom_v2.json` and the frontend AXIOM-V2 fixtures were deliberately NOT swept (they describe AXIOM-V2 paths, not our OMNIX module).

### Added
- **8 slice 15.3.7 Python test files classified per a verdict manifest** (`/tmp/slice-15.3.7-test-verdicts.md`):
  - 1 file PASSING (`tests/fabric/test_dispatch_tools_integration.py`, 3/3 green).
  - 3 files MIXED with per-test `@pytest.mark.xfail(strict=True, reason=...)` markers naming the exact missing slice 15.3.7 symbol: `tests/fabric/test_dispatcher_provider_override.py` (1 pass + 4 xfail on `dispatcher.dispatch(provider_override=…)`), `tests/fabric/test_real_tool_use.py` (3 pass + 2 xfail on `openai_compatible.call(tools=…)` and `dispatcher._tool_use_message_list`), `tests/graph/test_store_locking.py` (1 pass + 4 xfail on `GraphStore._lock` / `.locked_connection()` / serialized writes; the concurrent-writes test uses `strict=False` because it passes in isolation but fails under full-suite load).
  - 2 files module-level `pytestmark = pytest.mark.xfail(strict=True)` because every test in the file depends on the same unbuilt slice 15.3.7 surface: `tests/fabric/test_provider_error_detail.py` (2 tests, `body_text`/`body_json` response fields not yet emitted) and `tests/studio/test_action_dispatch_route.py` (10 tests, `/action/dispatch` route + `omnix.studio.server.get_provider_client` symbol not yet built).
  - 2 files BLOCKED-OUT-OF-SCOPE — moved to `tests/_blocked/studio/` with sibling `.WHY.md` files, because they cannot be xfailed: `test_ingest_resilience.py` hangs past 60s on an async deadlock in the studio server lifespan when `_ingest_block` raises, and `test_workspace_dedupe.py` segfaults Python 3.14 / sqlite3 during teardown (GraphStore.close races with the ingest cache thread). Both have P1 entries in `TODOS.md`.
- **`TODOS.md` (new):** seven P1 entries naming the exact symbol each xfailed/blocked test needs in order to unblock (e.g. `slice-15.3.7-provider-override-kwarg`, `slice-15.3.7-graph-store-locking`, `slice-15.3.7-action-dispatch-backend`).
- **`tests/_blocked/` directory convention:** opt-out collection via `pyproject.toml` `[tool.pytest.ini_options]` `norecursedirs = ["_blocked", ...]` (pytest defaults preserved explicitly because `norecursedirs` replaces rather than extends). Each blocked test has a sibling `<name>.WHY.md` documenting root cause + restore checklist.

### Internal
- Test suite: 481 → 488 backend passing (+7 from PASSING-bucket stashed tests landing) + 22 xfailed (the slice 15.3.7 spec markers) + 5 skipped (unchanged). 1 pre-existing positioning test (`test_readme_company_brain_opening`) still fails on main HEAD due to README rewrite drift — NOT caused by this PR; deferred to its own one-line dispatch. No new failures introduced by this PR.
- Six commits on the slice-21-8-tool-dispatch-namespace branch: backend moves + frontend moves + import retargets + test classification + cleanup + receipts rename + this version bump.
- The `wip-slice-15.3.7-and-misc-post-PR` stash is intentionally NOT dropped — kept as recovery insurance until this PR lands.

## [0.6.0] - 2026-05-16

### Changed
- **Namespace restructure (slice 21.7 phase B):** all OMNIX source modules now live under the `omnix.*` Python namespace package (`src/omnix/`). Top-level packages `src/agents/`, `src/parser/`, `src/graph/`, `src/axiom/`, `src/fabric/`, `src/providers/`, `src/find_bugs/`, `src/verify/`, `src/scan/`, `src/studio/`, `src/mcp/` were moved under `src/omnix/<name>/`. Public CLI surface (`omnix analyze`, `omnix grammar`, `omnix find-bugs`, `omnix verify`) is unchanged. Import paths inside the codebase updated throughout (302 file renames + 99 internal import-path updates). `omnix.py` shim at repo root handles both script invocation and `import omnix` usage so external integrators see a stable entry point.
- **pyproject.toml version reconciled** from stale `0.1.0` to the actual `0.6.0`. `omnix_version.py` was the de-facto version source; pyproject had drifted since first commit. Both now agree.

### Fixed
- **Turboscan filesystem-hygiene env propagation through forkserver (slice 21.7 phase C):** on Python 3.14+ the turboscan worker pool uses `forkserver`, which snapshots `os.environ` at first use. Subsequent updates to the parent's env never reach worker children, so per-codebase `OMNIX_FS_HYGIENE_*` config was being stripped at the worker boundary. Fix threads the hygiene env explicitly through `run_args` via a new `subprocess_env_overrides` key; `_run_verify_limited` applies it to the env dict handed to subprocess. Verified by `tests/scan/test_hygiene_integration_with_find_bugs.py` (2 passed, was 2 failed before).
- **`omnix grammar list` off-by-one (slice 21.7 phase C):** `suf = n[13:]` stripped one character beyond the 12-char `tree_sitter_` prefix, printing `tree_sitter_ava/ava` instead of `tree_sitter_java/java` for every language. Replaced with `n[len("tree_sitter_"):]`.
- **Forkserver env cleanup completeness — toggle pattern (slice 21.7 phase C.1, codex adversarial follow-up):**
  - `_run_verify_limited` previously only SET hygiene env keys via `subprocess_env_overrides` and never CLEARED them. A hygiene-disabled scan running after a hygiene-enabled scan in the same parent process could inherit stale `OMNIX_FS_HYGIENE_REPO_ROOT`/`_STRICT`/etc., causing hygiene findings to fire against the wrong repo. Fix: when `OMNIX_FS_HYGIENE_ENABLED` is absent from overrides, pop all `_HYGIENE_ENV_KEYS` from env before applying overrides.
  - `_child_verify` (Hypothesis-import fallback path) dropped `subprocess_env_overrides` entirely, reintroducing the staleness bug when that fallback fired. Fix: mirror `_run_verify_limited`'s pop-then-apply logic on `os.environ` inside the child.
  - New regression suite at `tests/scan/test_hygiene_env_toggle.py` (3 tests) exercises the toggle pattern and the fallback path.

### Internal
- Test suite: 478 → 481 passing (+3 from phase C.1 regression tests). 5 skipped (intentional env-gated perf tests + one parser_bridge placeholder).
- Frontend test suite: 248 passing.
- Codex adversarial review run on phase C surfaced two findings (HIGH + MEDIUM); both fixed in phase C.1 within the same PR.
