# Quality profile baselines (expected_range)

This document records **observed** per-grammar **mean quality** (aggregate `q` = `total_quality_score / total_files_parsed` in `grammar_profile` after a full `omnix analyze`) on real public codebases, as of **2026-04-25** (Phase 14b-2). It is **descriptive of the population** (P_2_1), not a target to tune weights toward (P_2_2). **quality_formula_version** remains **2**; only **metadata** was added to the JSON profiles.

**Note:** Future calibration runs (new commits, new Tree-sitter packs, or ingest changes) may shift these ranges. Re-run `omnix analyze` on the same commit SHAs for strict regression of `q` alone; graph size and file counts will still move with code changes.

## Repro (environment)

- OMNIX repo: path to this checkout; `OMNIX_INGEST_WORKERS=1` (matches typical single-thread apply path for apples-to-apples).
- Shallow clone: `git clone --depth 1 <url> /tmp/calib-…/<name>`; remove `/tmp/calib-*` between automation batches if disk is tight.
- **Java:** `pip install tree-sitter-java` (optional; not pinned in `pyproject.toml` today) — without it, `.java` is skipped and no `java` row is accumulated.
- **tree-sitter-c:** not required for 14b-2; C-only samples that fail to load the grammar are omitted from this document.
- **Generic profile:** `expected_range` in `generic.json` is populated from **Ruby** projects (scoring still uses `generic.json`; the evolution aggregate key in SQLite is `grammar_name='ruby'`, not `'generic'`.

## Per-language summary

| language    |  mean q |   std  |  min  |  max  | n_samples |
|-------------|---------|--------|-------|-------|----------|
| **python**  | 0.6154  | 0.0912 | 0.4512| 0.7074| 6        |
| **typescript** | 0.4924 | 0.1106 | 0.2757 | 0.6461 | 6  |
| **javascript** (see below) | 0.3732 | 0.1848 | 0.1085 | 0.5826 | 5 |
| **go**      | 0.6354  | 0.0387 | 0.5861| 0.6823| 5        |
| **rust**    | 0.7012  | 0.0969 | 0.5709| 0.8347| 5        |
| **java**    | 0.6802  | 0.0217 | 0.6484| 0.7078| 4        |
| **generic** (via Ruby) | 0.0215 | 0.0148 | 0.0021 | 0.0434 | 5 |

### JavaScript

Tree-sitter maps `.js` / `.mjs` / `.cjs` to the **TypeScript** grammar; **`grammar_profile`** uses **`grammar_name = 'typescript'`** for the aggregate, while per-file `compute_score_v2` can still use the **javascript** profile. The 14b-2 line for **javascript** in this table and in `javascript.json` uses **the same** aggregate `q` you see for those JS-dominant repos in `grammar_profile` (one row per run). That is a known **naming** split, not a second DB bucket.

## Sample codebases and commit SHAs

All URLs are `https://github.com/<org>/<repo>`; SHAs are **HEAD** of `git clone --depth 1` at run time (see `expected_range.samples[].commit_sha` in each profile JSON).

**Python (6):** django, flask, fastapi, requests, pytest, and **AXIOM-V2** (separate worktree) — the latter is required as a P_2_3 anchor.

**TypeScript (6):** react, vue, nest, axios, vite, **AXIOM-V2**.

**JavaScript (5, aggregate row `typescript` in DB):** lodash, preact, express, immer, date-fns.

**Go (5, kubernetes omitted per master 14b prompt):** moby (Docker engine), hugo, gin, cobra, prometheus.

**Rust (5):** ripgrep, alacritty, tokio, serde, exa (exa is archived upstream; still samples real Rust layout).

**Java (4, requires tree-sitter-java):** google/gson, google/guava, junit-team/junit4, apache/kafka. **Not** in the final table: spring-framework / elastic/elasticsearch in an early attempt without the Java pack (almost no `java` ingest).

**Generic / Ruby fallthrough (5):** rack, puma, sidekiq, sinatra, hashicorp/vagrant.

## AXIOM-V2 invariants (P_2_3)

Profile JSONs for **python** and **typescript** list **AXIOM-V2** in `expected_range.samples` with the Phase 14a / P_2_4 aggregate **q** values: **python ≈0.6831** (254.10 / 372), **typescript ≈0.6461** (115.66 / 179), commit `dd60430bc3012f830e7d448507ee8a75e61757a2` in the AXIOM-V2 tree used in-house.

## Weight recalibration

**None** in 14b-2. Observed `q` spans already overlap the profile weights; no miscalibration requiring weight edits was found under P_2_2.

## How to re-check `q` on a finished `omnix.db`

```sql
SELECT grammar_name,
       total_files_parsed,
       total_quality_score,
       (total_quality_score * 1.0 / total_files_parsed) AS q
FROM grammar_profile
ORDER BY grammar_name;
```

`nodes` / `edges` in `expected_range.samples` are from the same run (`SELECT COUNT(*) FROM nodes/edges`).

## Optional packs (not in default install)

| Pack / grammar | pip package | Used in 14b-2 |
|----------------|-------------|---------------|
| Java | `tree-sitter-java` | Yes (java rows) |
| Ruby | `tree-sitter-ruby` | Yes (generic / ruby rows) |
| C | `tree-sitter-c` | No (dry-run had 0 nodes) |

## Wall-clock notes (14b-1 post-fix)

Ingest time is no longer dominated by per-file `get_all_edges` on the main `GraphStore`. Multi-minute runs are now mostly **Tree-sitter + I/O** on very large trees (e.g. `moby`, `react`). A **&gt;10 min** cap was kept only as a *safety valve* in automation; 14b-2 did not drop large successful samples solely for duration.

## Full sample list (name → short ref)

| Sample | Organization / repository |
|--------|---------------------------|
| django | django/django |
| flask | pallets/flask |
| fastapi | tiangolo/fastapi |
| requests | psf/requests |
| pytest | pytest-dev/pytest |
| react | facebook/react |
| vue | vuejs/core |
| nestjs | nestjs/nest |
| axios | axios/axios |
| vite | vitejs/vite |
| moby | moby/moby (Docker engine) |
| hugo | gohugoio/hugo |
| gin | gin-gonic/gin |
| cobra | spf13/cobra |
| prometheus | prometheus/prometheus |
| ripgrep | BurntSushi/ripgrep |
| alacritty | alacritty/alacritty |
| tokio | tokio-rs/tokio |
| serde | serde-rs/serde |
| exa | ogham/exa |
| gson | google/gson |
| guava | google/guava |
| junit4 | junit-team/junit4 |
| kafka | apache/kafka |
| lodash | lodash/lodash |
| preact | preactjs/preact |
| express | expressjs/express |
| immer | immerjs/immer |
| date-fns | date-fns/date-fns |
| rack | rack/rack |
| puma | puma/puma |
| sidekiq | sidekiq/sidekiq |
| sinatra | sinatra/sinatra |
| vagrant | hashicorp/vagrant |
| AXIOM-V2 | in-house tree (path `~/AXIOM-V2` in local repro) |

This table is for human navigation; authoritative SHAs and numeric `q` are in the JSON `expected_range` blocks in `src/parser/quality_profiles/*.json`.
