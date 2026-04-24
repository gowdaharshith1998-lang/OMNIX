# AXIOM ML-DSA-65 (OMNIX)

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
- GitNexus, Axon, CodeGraph, code-review-graph all in the graph lane
- ZERO competitors sign code intelligence events with ML-DSA-65
- OMNIX moat: everything ABOVE the graph (vault, signed receipts, legacy migration, agent routing)
- Revised positioning: "The only code intelligence IDE where every AI-generated change is cryptographically signed"

### Day 3 target
- Integration #3: Provider Fabric port from AXIOM v2
- Layer between agents (future Integration #7) and vault keys (shipped)
- Responsibilities: policy-driven routing, failover, trust scoring, cost governance, telemetry, rate limit coordination
- Do NOT conflate with auto-detection (that was #2C, already done)
