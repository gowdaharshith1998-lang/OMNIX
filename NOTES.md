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
