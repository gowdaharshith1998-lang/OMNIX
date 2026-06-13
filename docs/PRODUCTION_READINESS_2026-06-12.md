# OMNIX Production-Readiness Audit — 2026-06-12

**Scope:** Full-repo multi-agent audit (9 scoped reviewers + adversarial verification) of OMNIX
`v0.6.1`, followed by remediation of the highest-impact confirmed findings. Local test suites
were restored on Windows (Python 3.13 + Node 24 + Temurin JDK 21) and run green except where noted.

**Verdict:** The core engineering is strong — FIPS 204 ML-DSA-65 signing is KAT-validated, the gate
runner never silently passes, ingestion isolates per-file errors, and crypto/SSRF/ingest hygiene is
genuinely good. The product is **not yet production-ready for real migrations** primarily because of
the cloud persistence gap (below) and a cluster of data-integrity bugs in the change-data-capture and
bulk-import paths. This pass fixed the data-integrity and trust-critical defects that are well-scoped
and locally verifiable; the cloud-persistence work is larger and is documented here as the top
remaining item.

---

## Test status (local, this machine)

| Suite | Result |
|-------|--------|
| Python `pytest` (full) | **1342 passed**, 84 skipped, 27 xfailed, 0 failed¹ |
| Vault `vitest` | 61/61 passed |
| Studio frontend `vitest` + `tsc --noEmit` | 270/270 passed, types clean |

¹ After the fixes below. The previously-flaky `test_scratch_mode_bootstrap_immediate` was a real
ordering bug (now fixed, see F8), not a test artifact.

---

## Fixed in this pass

| ID | Sev | Area | Finding | Fix |
|----|-----|------|---------|-----|
| F1 | Critical | dm/CDC | `DELETE` change events were replayed as the same generic insert-shaped write — source deletes never reached the target (silent divergence). | `replay_one` now branches on `event.op`: parameterized `DELETE`/`UPDATE` keyed on replica-identity (or before-image) predicate, `INSERT` only for inserts. New test asserts the emitted SQL verb. |
| F2 | Critical | dm/CDC | Multi-row transactions lost all but one row per table: the idempotency watermark deduped on the shared transaction LSN with `<=`, dropping rows 2..N as "re-deliveries". | pgoutput now stamps an intra-transaction `seq`; the watermark is the `(lsn, seq)` pair. New test replays a 3-row same-LSN transaction and asserts all 3 apply. |
| F3 | Critical | dm/bulk | Default bulk `COPY` path never committed — under a normal non-autocommit psycopg2 connection every COPY'd row was rolled back on close. | `_pg_copy` now commits (mirroring the INSERT path's error handling). Happy-path test asserts the commit occurred. |
| F4 | High | receipts/crypto | Seeding the test DRBG permanently hijacked the **process-global** ML-DSA signer, so every later keygen and every signing nonce became deterministic — order-dependent signatures and catastrophic nonce-entropy loss. | `keypair(seed=…)` now snapshots the live entropy source, seeds only for that one keygen, and restores `os.urandom` in `finally`. Keys stay deterministic; signing is always randomized. KAT + determinism tests pass. |
| F5 | High | dm/receipts | Signed receipts are written UTF-8 (`ensure_ascii=False`) but read back with the platform default encoding. On Windows (cp1252) any non-ASCII receipt content (e.g. the em-dash in an "Oracle SEQUENCE detected — flag_for_d2" warning) round-tripped as mojibake, **breaking signature verification and corrupting the predecessor-hash chain**. | All receipt/manifest/signature readers in both consumers + the checkpoint reader now decode UTF-8 explicitly. The two D-pipeline integration tests now pass on Windows. |
| F6 | High | security | The offline audit-kit verifier shipped to customers extracted bundles with unsanitized `tar.extractall()` — a tampered `.tar.gz` (`../../escaped`) could write outside the unpack dir on the auditor's machine. | Added a `_safe_extract` member sanitizer (rejects absolute paths, `..` traversal, and link members) into the bundled verifier source. New test builds a traversal archive and asserts the verifier refuses it and writes nothing outside. |
| F7 | Medium | parser/Win | `JavaSemanticEmitter` unresolved-symbol regex used `[^:]+` for the file group, so Windows paths (`C:\…`) truncated at the drive-letter colon and the structured-error parse failed. | Regex now matches the file group non-greedily up to the final `:<line> ::`. |
| F8 | Medium | studio | A freshly-subscribed WebSocket could receive `stats` frames before `bootstrap_start` (the per-connection stats ticker started before `_run_bootstrap`, which blocks on `ingest_event`), violating the bootstrap-first contract a real frontend relies on. | The stats ticker now starts only after bootstrap is delivered. Studio suite green. |
| F9 | — | CI/PR #63 | python-tests couldn't collect (cloud tests import PyJWT, only in the `cloud` extra); naming-pivot JS test drifted from its Python twin; two CodeQL path-injection alerts; Java gate needed a matching JDK. | CI installs `.[dev,cloud]`; pinned Temurin 21; reworded the naming-pivot assertion; restructured the studio path guards into the realpath+prefix shape CodeQL recognizes; dismissed 4 by-design localhost open-project alerts. **PR #63 is green.** |
| F10 | Critical | cloud | The orchestrator never persisted to Postgres — jobs/receipts/tenant state lived only in a process-local in-memory bus, so state was lost on restart and invisible across gunicorn workers and the Celery worker process; the Stripe webhook computed the new tier and discarded it; job-read endpoints had no tenant authorization. | New `cloud/store.py` durable layer (opt-in via `OMNIX_EVENTS_PERSIST`; in-memory stays the dev/test default). `events.publish`/`history` now persist and read job events + advance Job state through Postgres with a DB-authoritative seq, so `GET /v1/jobs/{id}` is correct across processes and survives restart. `record_job` is created before the first event; job reads are tenant-scoped (cross-tenant → 404, no existence leak); the Stripe webhook persists the resolved tier; inline production receipts are persisted. 7 new tests against file-backed SQLite prove durability across a fresh bus. |

---

## Top remaining work (not fixed this pass — larger or needs product decisions)

### Critical
- *(Fixed — see F10.)* Cloud Postgres persistence is now wired (opt-in). The one remaining piece of
  this finding is **live WebSocket fan-out across processes**: durable job *state/history* is now
  cross-process via the shared database (`GET /v1/jobs/{id}` is correct across workers), but the live
  `/ws/jobs/{id}` stream still only sees events published in its own process. Production multi-replica
  live streaming should add a Redis pub/sub fan-out (the in-memory bus remains the dev default); the
  durable DB is already the source of truth for replay.

### Second remediation wave — also fixed (F11–F18)
| ID | Sev | Finding | Fix |
|----|-----|---------|-----|
| F11 | High | Cost-runaway guard bypassed for any model missing from the pricing table ($0 → cap never trips). | Unknown cloud models costed at a conservative most-expensive-tier fallback (configurable); `ollama` stays free. Tests added. |
| F12 | High | Cloud CORS used `allow_origins=["*"]` with `allow_credentials=True` (spec-invalid + unsafe); Studio used unconditional `["*"]` and the Studio WebSocket had no Origin check. | Cloud debug → localhost-regex (credentialed), prod → configured origin; Studio → localhost-regex; Studio WS rejects non-localhost Origin/Host before accept. |
| F13 | High | DM consumers silently skipped signature verification when `public_key is None` despite `verify_signatures=True`. | d3 + d4 consumers fail closed (HALT). Regression test added. |
| F14 | High | `aiosqlite` (cloud test DB driver) declared in no dependency group. | Added to the `dev` extra. |
| F15 | High | README quickstart claimed `analyze` starts the Studio UI, but the frontend dist is not checked in (clean clone shows a build-notice). | Quickstart documents the one-time frontend build and clarifies the CLI path works without it. |
| F16 | Medium | Cloud OAuth state cookies hardcoded `secure=False` (sent over plaintext even in prod). | `secure` is now true outside debug. |
| F17 | Medium | Production Docker images ran as root; api/github-app had no `HEALTHCHECK`. | Both drop to an unprivileged user + add a `HEALTHCHECK`; github-app gains a `/health` route. |
| F18 | Medium | Runtime/generated/internal artifacts tracked in the public repo; pyproject had no license/classifiers; no `py.typed`. | Untracked + gitignored the SQLite WAL/SHM sidecars, the 2.6 MB generated graph JSON, the root PDF dump, `.codex/` gate reports, and `slice21_recon.md`; declared the source-available license + classifiers; shipped `py.typed`. |

### Second remediation wave — also fixed (continued)
| ID | Sev | Finding | Fix |
|----|-----|---------|-----|
| F19 | High | **Production ingest never produced cross-file `CALLS` edges** (confirmed by repro: a 2-file project where `app.main()` calls `lib.helper()` yielded 0 CALLS edges). Each file is parsed in an isolated per-file store, so calls only resolved within one file — the program graph was silently single-file for call relationships. | Added an **additive global second pass** (`_resolve_cross_file_calls`) to `ingest_unified_codebase`: after all per-file definitions merge, it rebuilds a global call index and re-runs the Python/TypeScript call pass against the merged store. Safe by construction — `add_edge` dedups (within-file edges untouched) and `_resolve_callee` prefers a same-file definition, so only genuinely cross-file calls gain their missing edge. Covers the dedicated-resolver languages (Python, TS/TSX); 2 new regression tests; full parser+graph suite green. |
| F20 | High | **Cutover authorization receipts signed with a fresh ephemeral keypair per call** — never anchored, so they proved nothing verifiable across processes/restarts. | `real_signer()` now loads a **persistent** ML-DSA-65 keypair (creating + persisting it once under `OMNIX_CUTOVER_KEY_DIR`, default `~/.omnix/keys/cutover/`, secret mode 0600) and caches it; receipts from any worker verify against the same published key. New test asserts the key is stable across signer instances and survives a simulated restart. |
| F21 | Medium | **Receipt-algorithm overclaim:** README marketed "post-quantum signed receipts for every finding or transformation," but per-finding and per-rebuild receipts are classical Ed25519 (ML-DSA-65 covers the scan manifests + DM migration chain). | Corrected the README claim to describe the actual hybrid scheme accurately rather than upgrading every per-item receipt to 3309-byte ML-DSA signatures (a deliberate size/perf tradeoff). |
| F22 | Medium | **`DESIGN.md` mislabeled:** it is a Linear.app visual/brand spec, but `docs/internal/README.md` listed it as "design notes for architecture decisions" — misleading to a reviewer; the same index pointed at the now-removed `slice21_recon.md`. | Relabeled `DESIGN.md` accurately as a visual/brand design reference (explicitly "NOT software architecture") and dropped the stale `slice21_recon.md` reference. |
| F23 | Medium | **Prompt-injection posture undocumented:** the rebuild prompt interpolates raw source from the (untrusted) migrated repo with no acknowledgment. | Documented the explicit posture in `prompt_template.py`: source is untrusted and deliberately un-sanitized because the six-gate verification pipeline — not prompt hygiene — is the security boundary; injected instructions can at worst produce gate-failing output flagged for human review, never smuggle unverified code through. |
| F24 | Medium | **Celery `start_pipeline` retries re-ran the entire non-idempotent pipeline** (re-ingest, re-emit receipts) on any failure or duplicate dispatch. | Added an idempotency guard (`store.job_already_finished`): the task skips when the persisted Job already reached a terminal success state (`complete`/`awaiting_cutover`). No-op when persistence is off (dev/test). 2 new tests. |
| F25 | High | **Turboscan worker-slot collision:** the slot keyed both the in-flight hygiene registry (`book[slot]`) and the Hypothesis DB dir, but was `hash((relp, fn)) % workers` — so two distinct targets running concurrently clobbered each other's registry entry (misattributed filesystem-hygiene events; one cleared the slot mid-run of the other) and shared one Hypothesis example DB (corrupted/cross-contaminated replay), contradicting the documented worker-isolation. | Assign each target a **unique** slot (its index), making both the hygiene-registry correlation and the Hypothesis DB dir per-target and collision-free. Scan suite green. |

### High — still remaining
- **Cross-file `CALLS` for non-resolver languages:** the F19 second pass covers Python and
  TypeScript (the languages with name-resolving parsers). Rust/Go/Ruby/generic still resolve calls
  only within a file; extending global resolution to them is follow-on work. Name-collision
  resolution (a short name defined in multiple other files) still picks the first global candidate —
  the pre-existing documented limitation, now also reachable cross-file.
- **DM Merkle-chain `predecessor_hash` is signed but never validated** by any consumer; substituted or
  reordered predecessors pass. *(Attempted this pass and backed out: the `predecessor_hash`
  convention is inconsistent across emitters/consumers — chainhash files use `next_hash(pred ++
  canonical)` while the consumer's own output uses plain `sha256(canonical)` — so validation needs a
  dedicated convention-unification pass first.)*
- **Optional crypto upgrade:** per-finding/per-rebuild receipts remain Ed25519 (F21 corrected the
  marketing to match). Upgrading them to ML-DSA-65 would make every per-item receipt post-quantum at
  the cost of ~50× larger signatures (3309 vs 64 bytes) — a product decision, not a bug.

### Medium / Low — still remaining
- Private signing keys stored unencrypted, guarded only by `os.chmod(0o600)` — a no-op on Windows.
  (Real encryption-at-rest / OS keychain integration is follow-on work.)

Full per-finding evidence (file:line) is preserved in the audit run output and can be regenerated.

---

## Known-good / explicitly out of scope
- GitHub Actions billing block (account-level, external).
- `tests/graph/test_store_locking.py::test_concurrent_writes_serialized` documented flake; its root
  cause (a single shared `sqlite3` connection opened `check_same_thread=False` with no locking) is
  confirmed and worth fixing but was left as tracked debt this pass.
- `slice-15.3.7` xfail backlog (intentional spec for unbuilt features); `AUDIT.md` (archived April doc).
