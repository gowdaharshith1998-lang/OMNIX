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

---

## Top remaining work (not fixed this pass — larger or needs product decisions)

### Critical
- **Cloud orchestrator never persists to Postgres.** Jobs, receipts, and tenant/tier state live only
  in a process-local in-memory bus (`cloud/events.py::_BUS`), despite docstrings promising Redis
  pub/sub and Receipt-table writes. State is lost on restart and invisible across the configured
  gunicorn workers and the Celery worker process — so job status breaks even at `--workers 1`
  (the runner publishes gate events into the worker's own `_BUS`, invisible to the API). This single
  gap cascades into the Stripe webhook dropping tier changes (below), cross-tenant job reads, and
  bypassable GitHub-App quota. **This is the #1 blocker for the cloud offering.** Recommended:
  persist `Job`/`JobEvent`/`Receipt` rows via the existing (currently-unused) async session scopes,
  and back the event bus with Redis so it spans processes.

### High
- **Cutover authorization "receipts" use an ephemeral per-process keypair** generated fresh each
  start and never anchored — they prove nothing verifiable, undermining the cutover trust gate.
- **Production ingest never produces cross-file `CALLS` edges:** `omnix analyze` and Studio route
  through a path that parses each file in an isolated store, so the globally-resolving call index is
  only ever single-file. The headline artifact (a cross-module program graph) is systematically
  incomplete in real use; the globally-resolving functions are test-only.
- **Turboscan worker "slots" collide:** slots are keyed by `hash(file,function) % workers` rather than
  executing-worker identity, so colliding targets share a slot entry and a Hypothesis DB dir under the
  default parallel scan — contradicting the documented worker-isolation claim.
- **DM Merkle-chain `predecessor_hash` is signed but never validated** by any consumer; substituted or
  reordered predecessors pass. Relatedly, both DM consumers silently skip signature verification when
  `public_key is None` despite a `verify_signatures=True` default.
- **Rebuild (per-node) and per-finding receipts are classical Ed25519, not the advertised
  ML-DSA-65.** README markets "post-quantum signed receipts for every transformation"; only some
  receipts are PQC. Either upgrade the signer or correct the marketing.
- **Cost-runaway guard is bypassed for any model missing from the pricing table** (cost computed as
  `$0`, daily budget cap never trips).
- **Studio `CORS allow_origins=["*"]` + ungated GET endpoints** can leak local filesystem paths to any
  website the operator visits while Studio runs; the WebSocket has no Origin check.
- **README quickstart is broken on a clean clone:** the two documented commands never build the React
  Studio, so `analyze` serves a JSON error instead of the UI.
- **`aiosqlite` is imported by the cloud tests but declared in no dependency group** — cloud tests
  fail at async-engine creation once CI billing is restored (the local fix here was installing the
  `cloud` extra; the dependency declaration should still be corrected).

### Medium / Low (selected)
- Private signing keys stored unencrypted, guarded only by `os.chmod(0o600)` — a no-op on Windows.
- Rebuild prompt interpolates raw legacy source from the (potentially hostile) migrated repo with no
  injection mitigation or documented acknowledgment.
- Production Docker images run as root; api/github-app images have no `HEALTHCHECK`; OAuth state
  cookies hardcoded `secure=False`.
- Celery `start_pipeline` retries re-run the entire non-idempotent pipeline.
- Runtime SQLite WAL/SHM artifacts and a 2.6 MB generated graph-data JSON and a root PDF dump are
  tracked in the public repo; `.gitignore` misses them.
- `pyproject.toml` declares no `license`/`classifiers` despite a custom source-available license;
  no `py.typed` marker despite the mypy config.
- Internal AI-agent scratch artifacts (`.codex/` gate reports, `slice21_recon.md`) and a borrowed
  Linear.app brand spec mislabeled as "architecture decisions" (`DESIGN.md`) are committed to the
  public portfolio repo.

Full per-finding evidence (file:line) is preserved in the audit run output and can be regenerated.

---

## Known-good / explicitly out of scope
- GitHub Actions billing block (account-level, external).
- `tests/graph/test_store_locking.py::test_concurrent_writes_serialized` documented flake; its root
  cause (a single shared `sqlite3` connection opened `check_same_thread=False` with no locking) is
  confirmed and worth fixing but was left as tracked debt this pass.
- `slice-15.3.7` xfail backlog (intentional spec for unbuilt features); `AUDIT.md` (archived April doc).
