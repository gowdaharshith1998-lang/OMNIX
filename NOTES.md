# AXIOM ML-DSA-65 (OMNIX)

## Slice 14 Debt

- Slice 14.5: `omnix analyze <path>` now serves the React Studio directly
  and auto-opens the workspace through `/api/studio/initial`. The legacy
  static viewer (`src/web/index.html`), its sidebar tests, and the
  viewer-engine generator were removed. `src/web/vault/` and
  `src/web/graph_data_axiom_v2.json` remain load-bearing and must stay.

- debt-16: viewerEngine.ts X-Ray helpers (buildXrayHTML, detectIssues, buildHealthBar,
  buildXrayAiSection, buildXrayFunctionHTML) superseded by XRayTab.tsx + lib/xray_*.ts.
  Delete in slice 17 cleanup pass once XRayTab.tsx has been live one week without regression.

## Slice 17b — Filesystem hygiene detector (2026-05-01)

### Round 2 — TURBOSCAN (2026-05-01)

- **Round 1 rollback:** Per-example repo snapshot/diff in `verify/runner.py` was removed from the hot path when `OMNIX_FS_HYGIENE_DELEGATED=1` (set by the TURBOSCAN orchestrator). Hygiene for parallel scans uses **watchdog** (`Observer` or `PollingObserver` fallback with log line `FALLBACK_POLLING`) plus a **multiprocessing `Manager().dict()`** slot registry so Layer 1 correlates inotify events with the in-flight verify target (serial path uses the same registry).
- **Package:** `src/scan/turboscan/` (orchestrator, budget planner, incremental state under `<repo>/.omnix/turboscan/`, worker-isolated Hypothesis dirs under `workers/<slot>/hypothesis`).
- **CLI:** `--no-turboscan`, `--all`, `--incremental`, `--plan`. Studio scan passes `incremental=True`.
- **E2E gates:** `tests/scan/turboscan/test_e2e_self_scan.py` R8/R9 run only when `OMNIX_TURBOSCAN_E2E=1` (full OMNIX self-graph timing + legacy comparison). **Wall-clock &lt;30s must be confirmed on target hardware** (stopwatch + Chromium) — not asserted in default CI.
- **Benchmark:** `benchmarks/turboscan_self_scan.py <codebase>`.

- Shipped: `src/scan/filesystem_hygiene.py` + per-example snapshot/diff inside `verify/runner.py` (when `OMNIX_FS_HYGIENE_ENABLED=1`). Findings merge into `find_bugs` with `dimension=filesystem_hygiene`. Studio drawer shows **FS-HYGIENE** + **DEEPEN** details; X-Ray Diagnostics shows **✓ filesystem clean** per file after a completed scan when that file has no hygiene findings on it.
- Live self-scan for `_prepare_verify_workspace_dir`: that helper only writes under `<repo>/.omnix/verify_workspace`, which is inside the declared sandbox, so the detector may correctly report **no** HIGH finding for it while still catching debt-19-shaped leaks (garbage dirname + `.omnix` under repo root). Slice **17c** owns containment fixes guided by hygiene results.
- Snapshot/diff is **non-atomic** vs concurrent writers (documented in `filesystem_hygiene.py`).

## Integration #11 (MEGA) — Evolution + database (ITER 4, 2026-04-25)

- **Per-codebase DB (Q2):** Studio analysis writes `<analyzed_root>/.omnix/omnix.db` (graph nodes/edges + evolution tables). This is the canonical Studio store for that tree. `omnix find-bugs` uses its codebase-local graph DB or creates one on first run; it does **not** fall back to `~/.omnix/omnix.db` unless you set `OMNIX_GRAPH_DB` to that path explicitly.
- **Schema:** `src/parser/evolution_schema.py` is applied idempotently from `GraphStore` (same SQLite file as the graph). Tables: `grammar_profile`, `query_pattern`, `pattern_mutation`, `unknown_extensions`.
- **Mutations:** Batched in `src/parser/evolution.py` — in-run observations only; `finalize_evolution_run(conn)` runs one `BEGIN`/`COMMIT` for SQL. Signed evolution JSON is written next to a **detached** ML-DSA-65 `.sig` file named `same_basename.sig` (so `SIG="${RECEIPT%.json}.sig"` works). If `~/.omnix/keys/secret.pem` is missing, promote/decay steps that require a receipt are **skipped** (P16); a warning is logged; no unsigned pattern changes for those steps.
- **P21:** Builtin rows in `query_pattern` with `added_by=builtin_hint` are never auto-decayed; only `auto_learned` patterns are eligible.
- **P13:** Evolution JSON contains only metadata (grammar, node_type, counts, scores, key fingerprint) — no source text or file paths from the repo.

## Provider Fabric: `parse_extract` task (Integration #11, ITER 3)

- **Task kind:** `parse_extract` is registered in `fabric` default `task_chains` with the same multi-provider order as other background tasks. It is used only by `src/parser/llm_fallback.py` to request **JSON-only** structured code facts (functions, classes, calls, imports) when universal AST quality is low. Router behavior is identical to any other `task_kind`: `chain_for_task` plus health and budget; no special Fabric code path.

## Polynomial / NTT layer

- **Day 1 (shipped):** Pure Python, `list[int]` coefficients for polynomials in R_q, NTT per FIPS 204 Algorithms 41–42. Throughput is acceptable for OMNIX provenance workflows.
- **Day 2 (optional):** A NumPy-backed coefficient layer would speed NTT and matrix-vector products by a large constant factor. NumPy is not a crypto library; if benchmarks require it, add a `numpy` extra and implement the same public APIs over `ndarray` without changing FIPS 204 behavior.

## Reflexion (iter 3)

No open failures at completion; the main correctness bug was `modpm` for even moduli (boundary at `α/2` vs `(α-1)//2`), which broke Power2Round and thus KAT public keys.

## Integration #2B — Vault UI redesign (2026-04-24)

- User-facing vocabulary sanitized. Three-tab interface replaced with provider-first surface. Underlying vault API unchanged.
- **Bug fix included: vault button wiring** — `createVaultUI` had stopped registering a `click` listener on `#btn-vault` (only the label was set), so the modal never opened. Restored `triggerButton.addEventListener('click', () => void open())`. Light-DOM host `#omnix-vault-modal-host` now uses `z-index: 10000` and `pointer-events: none` with `pointer-events: auto` on the shadow `.backdrop` so the overlay stacks above the Pixi canvas and remains interactive.

## Integration #2 (browser API vault, 2026-04-24)

- `npx vitest run tests/vault` — 36/36 pass (happy-dom + fake-indexeddb). IndexedDB test harness must `close()` the DB before `deleteDatabase` or hooks hang.
- `pytest tests/axiom/` — 24/24 still pass.
- Axiom bash acceptance: `python -m cli axiom` needs `--key /path/to/secret.pem` if the default `~/.omnix/keys/secret.pem` is missing (after `keygen --out` use that directory’s `secret.pem`).
- Manual Chromium smoke: not run in this environment; use DevTools to confirm no key material in console and ciphertext-only rows in `omnix_vault` / `omnix_vault_keys`.

## Integration #2C — API key auto-detection (2026-04-24)

- **What shipped:** Server-side `POST /api/vault/scan` and `POST /api/vault/scan/consume` in `omnix.py` (analyze server only, bound to 127.0.0.1). Scans `os.environ` for credential-looking values, allowlisted home config files and project `.env` (from the analyzed `target` path, not the server’s `chdir` web root), `~/.omnix/detected_keys.env`, and probes Ollama on `http://127.0.0.1:11434`. Plaintext is held in-memory 120s with single-use consume. ML-DSA-65 signed receipts in `~/.omnix/receipts/` (event JSON + `.sig` when `~/.omnix/keys/secret.pem` exists). UI: `ui-scan.js` with “Scan for existing keys” above the provider grid when vault is initialized and unlocked; import reuses `vault.addKey`. Tests: `pytest tests/scan/`, `npx vitest run tests/vault/`.
- **Skipped on purpose (broader auto-detection):** OS keychain (macOS Keychain, KWallet, Secret Service, Windows Credential Manager), 1Password/Bitwarden CLI, and browser extension bridges — all require different permissions, user consent flows, and often native bindings; the localhost-only, pattern-based scan is the minimal consistent threat model. Recursive directory search and git history were also excluded by spec to avoid exfiltrating large surfaces.
- **Reflexion (iter 3):** None required; scanner and tests passed after untangling a truncated `run_scan` and fixing project-root `.env` to use the analyze target (not CWD after `chdir` to `src/web`).

## Integration #3 — Provider Fabric (2026-04-24)

- **What shipped:** Python package `fabric` under `src/fabric/`: routing policy (`~/.omnix/fabric_config.json` with defaults on first run), provider health (last success within 60s), per-provider UTC daily budgets (check before call, commit cost after), transient retries and failover chains, idempotent in-flight dedup, in-memory telemetry ring (1000) + `GET /api/fabric/telemetry` + `GET /api/fabric/spend` (aggregated today/month per provider from telemetry + budget caps). Provider calls use **stdlib only** (`urllib.request`, `ThreadPoolExecutor`). HTTP routes on the analyze server: `POST /api/fabric/dispatch`, `GET /api/fabric/status`, `GET /api/fabric/telemetry`, `GET /api/fabric/spend`. Each dispatch writes a **metadata-only** ML-DSA-65 receipt (`call_*.json` + `.sig` when `secret.pem` exists); stderr warning if unsigned. Localhost-only enforcement uses `scan.handler.is_localhost_request` (peer IP + Host + Origin).
- **Vault bridge (spec C4):** The browser passes `provider_key` and optional `provider_keys` (for failover); nothing is persisted server-side; API keys are cleared after the HTTP call. No new runtime dependencies (`pyproject.toml` still `click` only); `setuptools` packages extended with `fabric`.
- **Deferred (Month 2+):** Streaming responses, token pre-estimation / reserved budget, trust scoring, dedicated agent-routing UI, Integration #3.5 localhost protocol to push keys without embedding in JSON.
- **Regression:** `pytest tests/fabric/` (25), `pytest tests/axiom/ tests/scan/` (48), `npx vitest run tests/vault` (40/40).

---

## Day 2 close (2026-04-24, ~01:00 local)

### Shipped
- Integration #1: AXIOM ML-DSA-65 pure-Python signing (24 pytests, 10/10 NIST KAT)
- Integration #2: Browser vault (PBKDF2 600K + AES-256-GCM, 36 vitest)
- Integration #2B: Provider-first UI redesign (hid crypto vocabulary)
- Integration #2C: Server-side API key auto-detection with signed receipts (24 pytest + 4 vitest)
- MIME fix in omnix.py (HEAD + GET + favicon 204)

### Proven in production (not just in tests)
- `omnix axiom verify` succeeded on a live scan receipt → full sign/verify chain is closed on real runtime data
- Plaintext grep returns 0 on live receipts → P11 holds outside unit tests
- Localhost-only enforcement: evil.com Host header → 403 (confirmed via curl)

### Known open items (not blockers, carry to Day 3)
- Scan UI button visibility in browser — server endpoint proven, UI surface untested at time of commit
- Remote URL pointed at lowercase `omnix.git`; fixed post-push to uppercase `OMNIX.git`
- index.html.canvas2d.bak removed in a follow-up commit; was pulled in accidentally by branch merge

### Velocity notes
- ~8 hours total elapsed for Integrations #1-2C
- At this pace the 30-day bet finishes in ~5-10 real days
- Day 10 checkpoint rule revised: checkpoint every 3 integrations (not every 10 days) because work is outpacing days
- Verification discipline: smoke tests must be human-witnessed end-to-end; unit-tests-green ≠ working product

### Strategic context (competitive landscape as of Apr 24 2026)
- Graphify released Apr 3 2026, 22k stars in 10 days — commoditized the "graph-of-codebase" layer
- Axon, CodeGraph, code-review-graph all in the graph lane
- To our current knowledge, no other product in this space signs graph/code-intelligence *events* with ML-DSA-65 in the same way as OMNIX; see README “Adjacent prior art” for related signing stacks (e.g. Sigstore, pqrascv-style attestation)
- OMNIX moat: everything ABOVE the graph (vault, signed receipts, legacy migration, agent routing)
- Revised positioning: "To our current knowledge, the only open-core code intelligence product that bundles universal Tree-Sitter + self-evolving query patterns + ML-DSA-65 signed audit trail + hybrid universal PBT + sandbox-isolated auto-fix in one shipping repo."

### Day 3 target
- Integration #3: Provider Fabric port from AXIOM v2
- Layer between agents (future Integration #7) and vault keys (shipped)
- Responsibilities: policy-driven routing, failover, trust scoring, cost governance, telemetry, rate limit coordination
- Do NOT conflate with auto-detection (that was #2C, already done)

---

## Day 2 close (2026-04-24, ~01:00 local)

### Shipped
- Integration #1: AXIOM ML-DSA-65 pure-Python signing (24 pytests, 10/10 NIST KAT)
- Integration #2: Browser vault (PBKDF2 600K + AES-256-GCM, 36 vitest)
- Integration #2B: Provider-first UI redesign (hid crypto vocabulary)
- Integration #2C: Server-side API key auto-detection with signed receipts (24 pytest + 4 vitest)
- Integration #2C-fix: Scan button visibility bug (state gate spec miss)
- MIME fix in omnix.py (HEAD + GET + favicon 204)

### Proven in production
- omnix axiom verify succeeded on a live scan receipt → full sign/verify chain closed on real runtime data
- Plaintext grep returns 0 on live receipts → P11 holds outside unit tests
- Localhost-only enforcement confirmed via curl (evil.com Host → 403)

### Known open items carried to Day 3
- None blocking. Scan button fix verified in browser at Day 2 close.

### Velocity notes
- ~9 hours total elapsed for Integrations #1, #2, #2B, #2C
- At this pace the 30-day bet finishes in ~5-10 real days
- Checkpoint rule revised: every 3 integrations (not every 10 days) because work outpaces days
- Human-witnessed smoke tests are mandatory before stamping integrations "done"

### Strategic context (Apr 24 2026 landscape)
- Graphify released Apr 3 2026, 22k stars in 10 days — commoditized graph-of-codebase layer
- To our current knowledge, no other product in this space signs graph/code-intelligence *events* with ML-DSA-65 the same way; see README “Adjacent prior art”
- OMNIX moat: everything ABOVE the graph (vault, signed receipts, legacy migration)
- Positioning: "To our current knowledge, the only open-core code intelligence product that bundles universal Tree-Sitter + self-evolving query patterns + ML-DSA-65 signed audit trail + hybrid universal PBT + sandbox-isolated auto-fix in one shipping repo."

### Day 3 target
- Integration #3: Provider Fabric — governance + routing + failover layer between agents and vault
- NOT auto-detection (that was #2C)
- Responsibilities: policy routing, failover, cost governance, telemetry, signed call receipts
- ~2-3 hours expected at current pace

---

## Agent architecture + product vision synthesis — April 24 2026

### The primary reframe

Everyone else is building smarter brains (LLMs).
We build the body and the thinking patterns that let an average brain
outperform a genius one.

LLM = commodity. Body = infrastructure. Reasoning modes = training.
Together = agent operating 2-3 std dev above underlying model.
Path from 46% SWE-Bench Pro to 90%+.

Use as primary positioning. Replaces "graph-native code intelligence."

One-liner for landing / deck / investor emails:
"Everyone else is building smarter AIs.
 We're building the body and the thinking patterns
 they need to actually use their intelligence."

### Layer 1 — The body (organs the LLM needs)

Eyes           = graph (sees structure, not text)                    [#6, #8]
Hands          = graph-mutation edits (proposed, applied atomically) [#7]
Ears           = structured event streams from runtime sandbox       [#7 EXECUTE]
Memory         = episodic tasks + skill library, signed chain        [post-30-day]
Nervous system = multi-provider fabric routing by organ/task type    [#3 done, wiring in #7]
Muscles        = containerized execution with capability gates       [#7]
Proprioception = confidence + budget tracking per step               [#7]
Spine          = AXIOM receipts on every organ's action              [#1 done]

### Layer 2 — Reasoning modes (how the brain uses the body)

1. Multi-hypothesis parallel reasoning
   Enumerate 5-10 hypotheses with cost-to-verify + prior.
   Verify cheapest first, not most likely.
   Research: BAVT (arXiv 2603.12634), ToT, GoT.

2. Bidirectional reasoning (forward + backward)
   Forward from entry point + backward from symptom.
   Cause = where chains converge.
   Research: AlphaProof-style convergent proof search.

3. Confidence-gated halting (metacognition)
   Agent tracks own confidence; <0.6 triggers clarify/consult/defer.
   Research: Metacognitive LLM Agents 2026, Self-Evolving Agents survey 2026.

4. Analogy retrieval from past episodes
   Query similar-shape past solves. Top-3 as context.
   Research: Memory-R1 2026, SimpleMem 2026, HiMeS 2026.

5. Abstraction ladder (explicit zoom primitives)
   ZOOM_OUT / ZOOM_IN / ZOOM_LATERAL as first-class tools.
   Backed by graph queries.
   Research: Hierarchical Planning in LLM Agents 2025-26.

6. Contrastive reasoning
   Propose 3 approaches, compare on axes, sign justification for pick.
   Signed justification = part of audit trail (unique to OMNIX).
   Research: Contrastive CoT (+10-15% code accuracy).

7. Programmatic reasoning
   Reason by writing + running code in sandbox, not prose, when task is
   verifiable.
   Research: PAL 2023 + PAL 2026 variants (+20-30% on verifiable tasks).

### Layer 3 — Verification loops (convergence architecture)

Single-shot ceiling: ~50%. Loop-to-convergence ceiling: 88-93%.

Integration #7 six-gate state machine:
  PROPOSE → EXTRACT → GENERATE_TESTS → EXECUTE →
    fail: FEEDBACK → loop
    pass: CONSENSUS (multi-provider, quadratic voting) →
      disagree: ADVERSARIAL_ATTACK → loop
      agree: GRAPH_CHECK (impact on callers/types/tests) →
        impact: REVIEW → loop
        clean: CONSISTENCY_CHECK (5 representations) →
          inconsistent: CLARIFY → loop
          consistent: SIGN → COMMIT

Cannot exit without passing all 6 gates.
Failing is cheap. Convergence is robust.

Stacked accuracy estimates:
  Baseline Claude SWE-Bench Pro:            46%
  + PBT verification (#5):                  57%
  + Execution feedback:                     72%
  + Multi-provider consensus:               81%
  + Graph-grounded verification (moat):     88%
  + Multi-representation consistency:       92%

### Integration #4 — Drill-down editor vision

Galaxy = navigation surface (home view).
Click node → Monaco editor opens for that function.
Inside editor: two modes, seamless:
  - Manual: user types, Monaco LSP features, familiar Cursor-like feel
  - AI: prompt box, agent writes, user reviews diff, approves or edits
Save → re-index graph → sign receipt → back to galaxy.

Monaco chosen over CodeMirror because once user drills in, familiar beats
differentiated. Galaxy already provided the differentiation. Inside
editor, muscle memory wins.

No mode picker. No "graph-first-ops cards." Standard text editor,
reached via galaxy, fed graph context to the AI, signed receipts on
save.

### Integration #4.25 — Progressive disclosure + visual hierarchy  [NEW]

Addresses the cluttered-feeling problem. Not a rebuild — improvements.

Progressive disclosure via zoom levels:
  Galaxy view    → ~20 constellations (modules/top folders)
  Constellation  → ~50 files within
  File view      → functions within
  Node           → drill down opens editor

Visual hierarchy:
  Node size      = centrality (PageRank on graph)
  Node brightness= recency of change
  Node color     = health (tests passing, errors, etc.)
  Edge thickness = call frequency or hotness

Estimate: 4-5 days of work. Between #4 and #4.5.
Do NOT rebuild rendering layer. Rendering (WebGL in Chromium,
AMD-driver-workaround known) is working. Add layers, don't replace.

### Integration #4.5 — Presence substrate  [NEW]

Lightweight real-time layer. Enables collaboration layers later.

Ships in 30-day bet:
  - WebSocket connection per user
  - Cursor position broadcasting
  - Galaxy presence (who's viewing which region)
  - Node-level presence (who's editing which function)

Uses Yjs or Automerge as CRDT foundation.
Estimate: ~3 days.

### Collaboration architecture — four scales

1. Human + AI in editor         → in 30-day scope via #4 + #7
2. Human + Human real-time      → presence only in 30-day (#4.5);
                                  full co-editing Month 2+
3. Agent + Agent                → in 30-day scope via #7 multi-agent loop
4. Team + Team workflows        → stubs in 30-day (data model only);
                                  full UI Month 2+

Decision split (2) and (4) full scope: defer until 30-day bet state at
Day 20 checkpoint.

Result = "multiplayer graph-native IDE where humans and AIs work
together with cryptographic provenance." That combination is not widely
shipped elsewhere as a single product.

### Design tooling choices

Figma          → sidebar, editor chrome, panels, onboarding
                 Hand off to Claude Code for implementation.
                 NOT Framer (React export pollutes codebase).

Gephi          → offline graph layout exploration against AXIOM v2 data.
                 Try force-directed, hierarchical, modularity.
                 Pick what reveals structure, then implement in PixiJS.

Shadertoy      → shader experiments for visual effects.
                 Port GLSL into PixiJS filters.

Spector.js     → WebGL debugging / performance profiling.
                 Browser extension.

PixiJS Playground → PixiJS-specific effect prototyping.

DO NOT:
  - Switch to Three.js, Cosmograph, Sigma.js mid-bet (rebuild trap)
  - Use Framer React export
  - Redo the galaxy rendering layer

### Updated integration roadmap (13 total, +1 = 14 with #4.25)

✅ #1  AXIOM ML-DSA-65 signing
✅ #2  Vault + Multi-Key API Manager
✅ #2B UI redesign "Connect your AI"
✅ #2C Scan + auto-detection
✅ #3  Provider Fabric
🔄 #3.5 Sidebar shell + Providers tab          ← TODAY
⏳ #4   Drill-down editor (Monaco + AI mode)
⏳ #4.25 Progressive disclosure + visual hierarchy  [NEW]
⏳ #4.5 Presence substrate (Yjs/WebSocket)          [NEW]
⏳ #5   PBT loop (Hypothesis + fast-check)
⏳ #6   Tree-Sitter 8 languages
⏳ #7   Multi-agent PEV (body + reasoning + loops)
⏳ #8   Graph→LLM bridge (CGBridge pattern)
⏳ #9   Active Inference planner (pymdp)    [KEEP — 5000x moat]
⏳ #10  OpenEvolve loop (OMNIX's own kernel) [drop-order 2]
⏳ #11  LFM2 edge deployment
⏳ #12  NCA self-healing visualization       [drop-order 1]

Drop order at Day 10 checkpoint if behind:
  1. #12 NCA viz (visual only)
  2. #10 OpenEvolve
  KEEP #9 Active Inference — only 5000x cost layer in world

Post-Day-30 roadmap:
  - Episodic memory store with signed chain
  - CPG with DFG + taint edges (security organ upgrade)
  - Analogy retrieval vector store
  - Hypothesis-tree + zoom + contrastive + programmatic reasoning
    modes wired into #7's agent prompts
  - Full real-time co-editing via CRDTs (collaboration scale 2)
  - Team review workflows (collaboration scale 4)
  - FHE + Confidential Computing enterprise path
  - Open AXIOM-Receipt-Format standard
  - SBIR/DARPA/DIU/AFWERX government channel

### Narrative anchor (for pitch/landing/investor emails)

The 100-Year Mirror frame:
  In 2126, engineers will find it absurd that:
    - AI wrote code without graph context
    - Code changes had no cryptographic provenance
    - Every codebase was re-parsed from scratch per LLM call
    - Dev tools competed instead of composing through a standard substrate
    - Fault localization waited for prod failures instead of graph prediction

OMNIX is building what 2126 takes for granted.

Narrative only. Not roadmap. Use in external surfaces.

### Decisions owed by Day 30

1. AXIOM name collision (current default: Option 1 — internal only)
2. Distribution model: closed-source SaaS vs open kernel vs standards-first
   (current default: closed product + open receipt format + free binary tier)
3. Demo reel / landing page timing (current: Day 30)
4. Collaboration scale 2+4 full scope (decide at Day 20 checkpoint)


---

## Day 5 — research day, no ship (2026-04-24)

**Attempted:** Galaxy visual upgrade matching docs/design-references/galaxy_reference.png
- #4.1: cluster overlay on existing renderer (visual delta insufficient)
- #4.1.5: full hub+leaf rebuild (over-clustered, only one cluster interactive)
- #4.1.6: cluster merge + idle drift + d3-force drop (still didn't land cleanly in browser)

**Outcome:** All three iterations stashed (`git stash list` → galaxy-4.1-4.1.5-4.1.6-incomplete-day5-revert).
Working tree reverted to `d6d2bcd`. Reference images backed up to ~/omnix-references/.

**What's preserved in the stash:**
- Pure data layer: Mulberry32-seeded Louvain + cluster merge (15→6 clusters), PageRank, FNV-1a cache key, 8-color palette, sunflower centroid layout, perpendicular Bezier control
- 127 passing vitest tests (clustering, pagerank, layout, regression, super_graph, interactivity)
- Test fixture: 684-node.json snapshot of OMNIX self-analysis
- Renderer scaffolding: nebula/filament/sparkle/hub-glow PIXI containers, perf-mode auto-downgrade ladder, runtime-injected #gx-perf-mode badge
- NOTES.md sections for #4.1 and #4.1.5

**Lesson:** Visual polish on a complex existing renderer carries 3-5x the time risk of greenfield work. The data layer was clean and shipped to test green on first try. The renderer integration with d3-force, existing pool, and AI trace overlay was where time disappeared. Future visual integrations: build the renderer in isolation first, integrate into existing app last.

**Bet status:** 50% shipped, ~16% time elapsed (Day 5 of 30). Still well ahead.

**Day 6 plan:** Integration #5 — PBT verification engine. Core product, not visual polish.

---

## Day 6 — Integration #5 PBT Verification Engine + #5.1 Package-Aware Loader (2026-04-25)

**Shipped:** `omnix verify <file> --function <name> --examples N` — graph-native PBT engine with cryptographically signed receipts.

**Modules (src/verify/):**
- signature.py — AST top-level def/async def extraction (skips *args/**kwargs, records defaults)
- caller_shape.py — read-only CALLS edges, literal type counts
- boundary.py — literal extraction with ≥2-caller filter (incl. unary minus)
- invariants.py — round-trip pair detection (`y = f(x); g(y)`)
- strategies.py — Hypothesis strategy synthesis from hints + caller signals
- runner.py — orchestrator with package-aware module loader + 4-level graph DB resolution
- receipt.py — ML-DSA-65 signed JSON receipts (reuses src/axiom/encoding.py)
- cli.py — argparse subcommand

**Loader (#5.1):** Walks up `__init__.py` to find package root, uses `importlib.import_module(qualified_name)` so files with relative imports load correctly. Restores sys.path on exit.

**Tests:**
- 34 pytest tests in tests/verify/ — all green
- 110/110 total pytest — all suites unchanged
- 85/85 vitest — sidebar/vault unchanged

**Receipt schema v1** (forward-compat envelope for #6 Bug Finder, #8 Auto-Fixer, #13 Bias Attestation):
{ axiom_signature, examples_run, failures[], graph_signals, kind, results[], strategies, target{file,file_sha256,function,lineno}, timestamp, version }

**🎯 First real finding:**
Smoke test on `src/axiom/encoding.py --function bitlen_u64` (our own ML-DSA-65 bit-length helper) found a contract gap in 50 examples:
- Input: `-1`
- Exception: `ValueError: bitlen expected nonnegative`
- Shrunk to minimum: 5 bytes
- Receipt: ~/.omnix/receipts/verify_2026-04-25T07-00-27.578675Z_bitlen_u64.json
- File SHA-256 captured, ML-DSA-65 signature present

This is the canonical demo: OMNIX found a contract gap in its own signing layer that 80+ existing tests didn't catch. **Pattern-matching scanners (Snyk, Semgrep, SonarQube, CodeQL) cannot find this class of issue.** OMNIX can.

**Spec correction:** Original prompt referenced `src/axiom/signer.py` (does not exist). Real signer module is `src/axiom/encoding.py`.

**Bet status:** 7 features in 6 days (~17% time, ~50% shipped). Ahead of pace.

**Day 7 plan:** #6 Bug Finder MVP — uses #5 to find real bugs in real OMNIX code, ships signed receipts, becomes the canonical product demo.

---

## Day 2 — Integration #6 Bug Finder MVP + recursion fix + conftest fix (2026-04-25 evening)

**Shipped:** `omnix find-bugs <path>` — whole-codebase PBT scan with graph-derived severity ranking and signed bundle receipts.

**Modules (src/find_bugs/):**
- walker.py — file discovery + filtering (.gitignore, ignore dirs, size limits)
- entry_points.py — detects `if __name__ == "__main__"` and decorator-based entry points
- severity.py — caller_count*2 + reachable*5 + failures*1 + public*1
- bundle.py — signed bundle receipt assembly (kind="find_bugs", schema v1)
- runner.py — orchestrator with self-recursion guard
- cli.py — argparse subcommand

**Recursion fix during smoke run:**
- src/verify/runner.py: zero-arity functions skipped (status="skipped_zero_arity"). Previously _run_zero_arity invoked them with no args, causing recursion when omnix.py:main was scanned.
- src/find_bugs/runner.py: skips functions where file is omnix.py entry, OR function is named `main` in a file with `if __name__ == "__main__"`. skipped_main array in bundle for transparency.

**Conftest fix:**
- conftest.py at repo root puts project root on sys.path so legacy tests (tests/fabric, tests/test_parser) collect under `pip install -e .` setup.

**Tests:**
- 129 pytest total (was 110 after Day 1)
  - 35 tests/verify/ (was 34, +1 zero-arity skip test)
  - 18 tests/find_bugs/ (new)
  - rest unchanged
- 85 vitest unchanged

**Smoke (tests/find_bugs/fixtures/sample_codebase):**
- Scanned 3 files, 3 functions
- Found unsafe_div (ZeroDivisionError on `/0`)
- Severity score 2, exit 1, 0.2s wall time

**Real-world `find-bugs ~/omnix` smoke:** runs without recursion now, but Hypothesis crashes on Click-decorated CLI commands. **Known limitation #6.1:** framework-decorated functions (Click, FastAPI, async routes) need to be skipped before PBT runs them. Tomorrow's first task.

**Cleanup:** deleted stale `_apply_canvas2d.py` (one-shot script from galaxy attempts).

**Bet status:** 8 features in 2 days. PBT engine + Bug Finder MVP shipped. First two real bugs found in own codebase (bitlen_u64 yesterday, zero-arity recursion today). **Next:** #6.1 framework-decorator skip → real-world `find-bugs ~/omnix` demo.

---

## Day 2.5 — Vault Auto-Detect + Custom OpenAI-Compatible (2026-04-25 night)

**Shipped:** Frontend vault expanded from 4 providers to 16+ with paste-time auto-detection.

**New module:** `src/web/vault/providers.js` — centralized provider catalog
- 16 built-in providers: anthropic, openai, google, ollama (existing) + xai, groq, perplexity, openrouter, deepseek, mistral, cohere, together, fireworks, replicate, huggingface, cerebras
- `detectProvider(key)` returns `{ matches, confidence: 'exact'|'ambiguous'|'none' }` based on regex patterns + priority resolution
- `custom_openai` escape hatch — never auto-detected, requires user-provided base URL + Bearer key, validates via `${baseUrl}/models`

**UI integration (src/web/vault/ui.js):**
- "Connect your AI" modal with grouped grid: POPULAR (6) / More providers (10, collapsible) / CUSTOM ENDPOINT
- Paste handler: auto-selects on exact match, "Did you mean?" picker on ambiguous, falls through to Custom on unknown
- Per-provider color circles + monogram letters
- Save-anyway path on validation failure (P15/P16 preserved)

**Compliance preserved (no key leaks):**
- P2/P15 — keys never sent to OMNIX backend, browser → provider only
- P16 — error messages never include key value
- P22 — never log key values
- Custom endpoint stores `base_url` as additive optional field (no schema migration)

**Tests:**
- 106 vitest (was 85, +21 new): test_detect.spec.js + test_validators.spec.js
- 129 pytest unchanged

**Bet status:** 9 features in 2 days. Vault is now usable by 95%+ of LLM API holders (was ~50% with 4 providers). **Next:** #6.1 framework-decorator skip → real-world `find-bugs ~/omnix` demo, then galaxy v3 reference saved for Day 7+.

## Day 3 first decision (deferred from Day 2 close)
Pick one: (a) Provider Fabric port from AXIOM v2 (the original Day 3),
          (b) Monaco IDE shell (the 'proper UI' question that started this session),
          (c) Demo recording — find-bugs end-to-end on src/axiom with signed bundle
Recommendation: (c) first — 30 min, gives you a shippable artifact for landing/pitch.

---

## Day 4 close (2026-04-25, evening)

### #11-MEGA SHIPPED
201+ pytest green. Universal language
code intelligence + signed self-evolution + sandbox-isolated auto-fix. Each layer has prior art (see README “Adjacent prior art”); the product claim is the **combination** shipped in one repository.

Real production artifacts on AXIOM-V2:
- 10 ML-DSA-65 signed evolution receipts
- decorated_definition pattern promoted with +0.34 quality delta
- Receipt example fields: kind, grammar, mutation, node_type, evidence,
  key_fp (sha256 of pubkey), schema_version, observed_at

### Polish-pass list (file as integrations #11-MEGA-A through D + #11.6)
- A: TS universal-pathway quality calibration (0.42 in production)
- B: subprocess.Popen getattr trick → # nosec annotation
- C: NOTES.md threat model section for Layer 6/7
- D: Add explicit added_by field to evolution receipt schema
- #11.6: Implement actual cargo fuzz / go test -fuzz / JQwik runners

### Bet status (Day 4 close)
Day 4 of 30. ~80% of 12 integrations shipped. Down to:
- #4 Monaco IDE shell (5-7 days, the "proper UI")
- #7 Multi-agent PEV (3 days)
- #8 Graph→LLM bridge (3 days, may be partly absorbed by #11-MEGA L3)
- #11.5 LFM2 edge (1-2 days)

Drop list final: #9, #10, #12.

Realistic bet finish: Day 12-15 not Day 30. Slack room for polish pass.

### Day 5 first decision (deferred from Day 4 close)
Pick one: (a) Demo recording (30 min, gives shippable artifact for
launch) → recommended. (b) #4 Monaco IDE shell. (c) #7 Multi-agent PEV.

## Historical Quality Formulas

### Formula v1 (Days 1-5 of bet, schema_version 1 and 2)
- **Active:** Days 1-5 (commits up to and including 42cc3d6)
- **Receipts produced:** ~10 evolution receipts on AXIOM-V2 (python: 7 mutations, typescript: 3 mutations)
- **Formula:**
  ```
  score = (function_count >= 1) * 0.30
        + (call_edge_count >= 1) * 0.20
        + (import_count >= 1) * 0.20
        + non_synthetic_names_present * 0.20
        + line_density * 0.10
  ```
- **Properties:** language-agnostic, biased toward Python-shaped code, under-counted TypeScript type-only files.
- **AXIOM-V2 baseline q values:**
  - **python:** 0.73 (9 patterns, 7 mutations, 371 files)
  - **typescript:** 0.42 (6 patterns, 3 mutations, 353 files)

### Formula v2 (Day 5+, schema_version 3)
- **Active:** from the Phase 3 feature commit forward (receipts carry `quality_formula_version`, `profile_grammar`, `profile_version`)
- **Per-grammar profiles in** `src/parser/quality_profiles/`
- **Profiles shipped:** 7 modern (python, typescript, javascript, go, rust, java, generic), 3 legacy (cobol, hlasm, fortran) — see `docs/LEGACY_LANGUAGE_SUPPORT.md`
- **Roadmap (Integration #15):** rpg, pl/i, jcl, vb6 — these require custom grammars not yet in the tree-sitter integration path; **not** supported today
- **TypeScript improvement:** +0.23 absolute, +55% relative (driven by `interface_declaration` / `type_alias_declaration` / `enum_declaration` nodes now contributing signal, plus build-output exclusion in the file walker)

## AXIOM-V2 baseline q values

### Phase 3b baseline (DEPRECATED — pre-skip-tracking)
- python: 0.7266 (372 files, 270.30 total quality score)
- typescript: 0.6524 (179 files, 116.78 total quality score)
- Note: these numbers included files that Phase 13.5's trust fix correctly identified as no-grammar/binary/build artifacts. They overcounted total_quality_score because skipped-but-counted files contributed weakly-positive partial scores.

### Phase 14a baseline (CURRENT — post-skip-tracking)
- python: 0.6831 (372 files, 254.10 total quality score)
- typescript: 0.6461 (179 files, 115.66 total quality score)
- Reproducible with: `cd ~/AXIOM-V2 && rm -f omnix.db && OMNIX_INGEST_WORKERS=1 python3 ~/omnix/omnix.py analyze . --no-open ; sqlite3 omnix.db "SELECT grammar_name, total_quality_score, total_files_parsed FROM grammar_profile WHERE grammar_name IN ('python','typescript');"`
- Both serial-1 and parallel-11 produce IDENTICAL output to 6 decimal places (verified Phase 14a HALT 2 Track A).

### Forward stability invariant (Phase 14a P_2_4 update)
- "Parallel output == serial output" within ±0.000001 per grammar
- "Today's run == previous run on same code" within ±0.0001
- Old "compare to Phase 3b NOTES baseline" gate is RETIRED. The Phase 3b numbers reflect a pre-skip-tracking state of the world that we deliberately moved past in Phase 13.5.

## Integration #15: Custom Grammar Pack (deferred)

OMNIX does **not** ship RPG, PL/I, JCL, or VB6 parsers today. This table is a **roadmap and market** reference only. Real grammar work is a multi-week Integration #15 effort.

| Language            | Traction / context                                      |
|--------------------|-----------------------------------------------------------|
| **RPG (IBM i)**    | $$$$ — IBM Project Bob March 2026 GA                     |
| **PL/I**           | $$$ — banking, insurance                                  |
| **JCL**            | $$$ — every COBOL deployment needs it                    |
| **VB6 / Classic ASP** | $$ — older enterprise                             |

**Grammar status:** not integrated in this repository; `docs/LEGACY_LANGUAGE_SUPPORT.md` describes shipping vs deferred languages.

## Phase 14b-2 — quality profile calibration (2026-04-25)

- **Procedure:** `git clone --depth 1` of each sample into `/tmp/calib-*` (cleared before runs); `OMNIX_INGEST_WORKERS=1` `omnix analyze . --no-open`. Per-codebase &gt;10 min wall time is used only as a *safety valve* (log and continue); 14b-1 speedup made multi-minute ingests the exception, not the rule. Very large codebases (e.g. `moby`/`react`) are included intentionally when they complete within a generous timeout.
- **Go / kubernetes:** The master 14b prompt still treats **kubernetes** as a manual skip (RAM on commodity hardware). **14b-2** uses **docker** (`github.com/moby/moby` clone) plus **hugo, gin, cobra, prometheus** — *not* `kubernetes/kubernetes`.
- **Java:** The optional **`tree-sitter-java`** package is *not* an omnix `pyproject` dependency. An early 14b-2 attempt on **spring-framework** / **elasticsearch** (without the pack) produced &lt;20 `nodes` and *no* `java` `grammar_profile` row (`.java` skipped with “grammar not installed”). **After** `pip install tree-sitter-java`, calibration used **gson, guava, junit4, kafka (apache/kafka, shallow clone)**, n=4 — meets P_2_4 n≥3. No fourth Java sample is forced; spring/elasticsearch were *not* used for the final table because the reliable runs were the four above.
- **C / lodepng / kqueue (dry run):** With `tree_sitter_c` *not* installed, shallow clones produced **0** `nodes` / `grammar_profile` for pure-C samples; C calibration is *not* in 14b-2 until `tree-sitter-c` is available in the environment; **not** a profile weight recalibration (P_2_1 / P_2_2).
- **generic** `expected_range` is measured on **Ruby** (rack, puma, sidekiq, sinatra, vagrant): **scoring** still uses `generic.json` (no `ruby.json`); **`grammar_name` in the DB** is `ruby` for `observe_parse` aggregates, not the literal `generic`.
- **No weight recalibration** in 14b-2: only additive `expected_range` metadata and `quality_formula_version: 2` on JSON profiles. **docs/QUALITY_PROFILE_BASELINES.md** lists every sample commit and per-language `mean`/`std`/`n_samples`.

## Phase 14b-3 — incremental re-analyze (Merkle-style) — 2026-04-25

- **State:** `omnix.db` has a `meta` table: `omnix_version`, `schema_version` (e.g. `3`), `profile_hash` (content hash of concatenated sorted `src/parser/quality_profiles/*.json`). `file_paths` that disappear from disk are removed from the graph; per-file content digests skip re-parse when unchanged. Full invalidation logs to stderr: profile bump (“quality profiles updated…”), or version bump (“upgraded from X to Y…”). `--force` bypasses cache.
- **HALT 14b-3 (sample, `/tmp/scale-django`, 2026-04-25, `OMNIX_INGEST_WORKERS=8`, laptop):** **cold** ~14 s, **warm** (no source changes) ~3.8 s, **`--force`** ~13 s. **Profile / version invalidation:** `tests/graph/test_file_hashes.py` (`test_profile_change_invalidates_cache`, `test_version_bump_invalidates_cache`). **Tests (evolving):** see Phase 14b-4 for current `pytest` count; Merkle + tree-cache tests.

**Backlog (14c / 15+):**

- **Phase 15:** Investigate **generic profile under-crediting** in dynamic-dispatch languages (e.g. Ruby `q` anomaly ~0.02 in some codebases).
- **Docs:** **TypeScript** and **JavaScript** both use `grammar_name='typescript'` in `grammar_profile` while per-file quality scoring uses the correct per-extension profile; document for operators.
- **Deps:** **Pin** `tree-sitter-java`, `tree-sitter-go`, `tree-sitter-rust` in `pyproject.toml` (Phase 14c+).

## Phase 14b-4 — Tree-sitter parse LRU + incremental reparse (2026-04-25)

- **Code:** `src/parser/tree_parse_cache.py` — per-process `parse_tree_cached(grammar_id, file_key, parser, source)`; **LRU** upper bound 1000 `(grammar_id, file_key)` entries; `get_shared_parser(grammar, language)`; **identical** bytes reuse the same `Tree` (pass1/pass2/quality counts share one parse). When *bytes* at a key change, the prior `Tree` is used as `old_tree` (Tree-sitter incremental API). **INFO** logging at 101, 200, …, 1000 cache entries (plus `evicted_total`) so a pathological Studio working set is visible *before* hard RSS limits.
- **Wiring:** `python_parser`, `typescript_parser` (`ts` / `tsx` cache keys), `universal` (rust + generic; `ts`+`is_tsx` in `_count_syntactic`), `ingest_dispatch` `top_level_syntactic_types` (shares the same key as the ingest `rel`).
- **HALT 14b-4 (min of 20 runs, ~48 KiB Python, tail append, sample laptop):** **full** ≈3.7 ms, **incremental** ≈1.4 ms, **speedup** ≈2.8× (small edits and mid-file changes vary; 50 kiB is mostly noise vs Tree-sitter core cost).
- **Tests:** `python -m pytest tests/` — **273** passed, 1 skipped. Tree parse cache: `tests/parser/test_tree_incremental.py`.
- **HALT 14b-final — live profile invalidation (content hash):** *mtime-only* `touch` is **insufficient**; e.g. `echo >> src/parser/quality_profiles/python.json` to append a newline. **Warm** `omnix analyze /tmp/scale-django` ~3.7 s → **after profile byte change** stderr: `OMNIX: quality profiles updated since last analyze, re-parsing all files (one-time cost on first run after upgrade)`; wall ~**15 s** (full re-parse on same tree). `git checkout --` the profile to restore.
- **Commit message notes (per master review):** include **(a)** 14b-3 *side fix* — `begin_batch` commits to flush implicit transactions from standalone writes before `BEGIN` (14a class bug surfaced by Merkle skip paths). **(b)** 14b-1/parallel: **parallel-8** ~**13.6 s** vs **serial-1** 19.25 s on **Django** (≈28% faster) — prior 14a “parallel regresses on small-file codebases” is addressed by the SQL/batch scoping so IPC is not dominated by main-thread per-file work. **(c)** **14b-4** Tree-sitter LRU + incremental, Studio-oriented cache cap, INFO past 100 entries.

---

