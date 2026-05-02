# Slice 18c — Grammar Visibility

**Tag**: `v0.4-grammar-visibility`  
**Shipped**: 2026-05-02 → 2026-05-04 (4 steps)  
**Test counts at close**: 368 Python passed, 5 skipped + 168 frontend passing

## TL;DR

Universal-parser visibility was CLI-only and opaque. Slice 18c adds **`omnix grammar status`**, five **read-only localhost HTTP routes** backed by `grammar_status_query.py`, a restored **`omnix analyze`** click path, and a **Studio Grammar Health** left drawer so operators can see grammars, mutations, unknown extensions, LLM budget, and verify evolution receipts without spelunking SQLite.

## What shipped

### Step 1 — `omnix grammar status` CLI

`omnix grammar status` with `--db`, `--grammar`, `--json`. Read-only SQLite; walks up for `.omnix/omnix.db`. Exit codes: `0` ok, `1` no DB / cannot open, `2` no grammar rows, `3` query failure. Emits the same payload keys the API uses for grammar rows (`grammar_name`, `files_parsed`, `avg_quality`, `parse_modes`, `active_patterns`, `recent_mutations_30d`, `last_evolution_receipt`) plus `unknown_extensions`, `unknown_extensions_top3`, `llm_fallback`.

### Step 2 — Backend grammar API

Five routes in `src/studio/server.py`: `GET /api/grammar/status`, `GET /api/grammar/mutations`, `GET /api/grammar/unknown-extensions`, `GET /api/fabric/llm-budget`, `POST /api/grammar/verify-receipt`. Shared queries in `src/parser/grammar_status_query.py`. All **read-only**; grammar GET/POST guarded to localhost (`403` otherwise). Unknown-extension strings sanitized at write; corrupt UTF-16 paths surface as optional `raw_bytes_hex` on the **unknown-extensions** route.

### Step 2.1 — `omnix analyze` restored

Regression from step 1: `analyze` was missing from the Click CLI. Restored with lazy dual-context import in `src/cli.py` so pip-installed and repo-root invocations both resolve.

### Step 3 — Studio Grammar Health drawer

`GrammarHealthDrawer` + `grammarApi.ts`; left rail entry **Grammar Health** (between Receipts and Settings). Polls four GET routes every **10s**; **Verify** POSTs `receipt_path` to `/api/grammar/verify-receipt`. Per-section loading / error / empty; inline ✓/✗ after verify.

## API surface

| Route | Method | Returns (top-level keys from live API) |
|-------|--------|----------------------------------------|
| `/api/grammar/status` | GET | `db_path`, `generated_at`, `grammars[]`, `unknown_extensions[]`, `llm_fallback` |
| `/api/grammar/mutations` | GET | `db_path`, `generated_at`, `mutations[]` |
| `/api/grammar/unknown-extensions` | GET | `db_path`, `generated_at`, `total`, `extensions[]` |
| `/api/fabric/llm-budget` | GET | `generated_at`, `budget_total`, `budget_remaining`, `calls_today`, `available` |
| `/api/grammar/verify-receipt` | POST | `receipt_path`, `sig_path`, `verified`, `verifier_output`, `verified_at` |

**`grammars[]` items:** `grammar_name`, `files_parsed`, `avg_quality`, `parse_modes`, `active_patterns`, `recent_mutations_30d`, `last_evolution_receipt`.

**`mutations[]` items:** `grammar_name`, `node_type`, `action`, `observed_at`, `receipt_path`, `sig_path`, `receipt_exists`, `sig_exists`.

**`extensions[]` items (unknown-extensions route):** `ext`, `first_seen_at`, optional `raw_bytes_hex`.

**Status route `unknown_extensions[]`:** summary shape `{ ext, count }` (distinct from the full `extensions` list on the dedicated route).

## CLI surface

| Command | Flags | Exit codes |
|---------|-------|------------|
| `omnix grammar status` | `--db`, `--grammar`, `--json` | 0 ok · 1 no DB · 2 no grammar data · 3 internal |

## Studio surface

Open **Grammar Health** on the left rail. The drawer loads LLM budget, grammars table, recent mutation cards, and unknown-extensions list; each section tolerates its own fetch failure. **Verify** only runs on click; result tooltip uses `verifier_output`.

![Grammar Health drawer](docs/images/grammar-health-drawer.png)

Hg: add `docs/images/grammar-health-drawer.png` in a follow-up commit (screenshot not in repo yet).

## Architecture decisions

- Read-only HTTP surface in 18c — no grammar mutation API here.
- **Polling** (10s), not WebSocket — data changes on minute scale.
- **Receipt verify** reuses canonical receipt-dir resolution and subprocess verifier; same trust boundary as evolution receipts.
- **UTF-16 surrogate sanitization** at `record_unknown_extension` so JSON and UI never break on corrupt DB text.
- **Lazy imports** for grammar/analyze in `src/cli.py` to survive dual install layouts.

## What we learned

- Pip vs repo-root import paths bite whenever new Click commands land; lazy sub-imports contain the damage.
- Drawer pattern (Files → … → Settings) scales; new operator surfaces should stay in that shell.
- Doc and code drift on field names (`action` vs `mutation_kind`, `extensions` vs `unknown_extensions`) — **sample live JSON** before writing prose.

## What's deferred

- **Slice 18d** — per–find_bugs LLM receipts (Compliance Vault unlock); architecture TBD.
- Drill-down from a mutation into files (slice 15 territory).
- Sort/filter on grammar tables; optional Rust hot path (18e) when pulled by workload.

## Next

**Slice 18d** — cryptographic receipts on `find_bugs` / LLM Layer 6 output, verifiable with the same receipt machinery as evolution. Revenue-bearing; schedule an architecture block before dispatch.
