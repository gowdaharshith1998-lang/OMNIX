# D1 — AI Schema Understanding (Implementation Notes)

## Status

D1 is available as a DM library surface. It emits a signed
`column-mapping.json` and flags uncertain mappings for operator review.

## EARS contract

> **When** a customer provides a legacy schema + target schema for migration,
> the system **shall** (1) parse both schemas dialect-aware, (2) extract per-column
> metadata + code-graph usage, (3) compute semantic embeddings, (4) match
> legacy ↔ target with confidence scores, (5) emit a signed
> `column-mapping.json`, (6) flag low-confidence mappings for operator review.
>
> **When** confidence is below `0.85`, the mapping shall be marked
> `status="low_confidence"` and `requires_operator_review=true`.
>
> **Where** no semantic match exists, the mapping shall be
> `status="no_match"` with explicit reason.

## Pipeline stages

### 1. Parse
`ddl_parser.parse(ddl, dialect)` returns `SchemaSpec | ParseFailure`.
Per-dialect modules under `dialects/`:

* `postgres.py` — handles `CREATE TABLE`, `CREATE INDEX`, `ALTER TABLE ADD
  CONSTRAINT`, `COMMENT ON COLUMN`. Quote-aware (`"..."`).
* `mysql.py` — backtick identifiers, `ENGINE`, `CHARACTER SET`, `COLLATE`,
  `AUTO_INCREMENT`, `UNSIGNED`.
* `oracle.py` — `NUMBER(p,s)` precision/scale, `VARCHAR2`, Oracle `DATE`
  (includes time, no TZ — `flag_for_d3=True`), `TIMESTAMP WITH TIME ZONE`.
  Sequences and triggers surface as parse warnings.
* `mongodb.py` — JSON-Schema (`$jsonSchema`) → `TableSpec`; nested object
  properties become dot-paths; arrays flagged `flag_for_d3=True`.

### 2. Metadata
`column_metadata.extract(schema, conn)`:
* Verifies the connection is **read-only** (PG `SHOW transaction_read_only`,
  MySQL `@@read_only`, Oracle `V$DATABASE.OPEN_MODE`). Halts with
  `ReadOnlyError` otherwise.
* Samples up to 100 distinct non-null values per column via parameterized
  SQL. Identifiers are routed through `quote_ident()` which rejects any
  quote character in the input.
* Bridges to `codebase_memory_bridge.lookup_column_usage` — pure read.

### 3. Codebase-memory bridge
The bridge attempts `from omnix import codebase_memory`. If the module is
not deployed it records that condition as `confidence_note` rather than
silently returning empty.

### 4. Embed
`column_embedder.embed(ctx)`:
* Lazy-loads `sentence-transformers/all-MiniLM-L6-v2` (384-dim).
* Deterministic prompt template (see source).
* `set_embedding_backend()` lets CI swap in a hash-based deterministic
  backend when model weights are unavailable in CI. The hash backend
  preserves the determinism contract — it just isn't semantically
  meaningful for cross-name similarity.

### 5. Match
`semantic_matcher.match(legacy_ctx, target_ctx)`:
* Computes pairwise cosine similarity.
* Solves Hungarian assignment via `scipy.optimize.linear_sum_assignment`.
* Applies thresholds (default `0.85` ok / `0.60` floor / `0.05` ambiguity
  spread; `OMNIX_DM_CONFIDENCE_THRESHOLD` overrides).
* Invariant: `len(output) == len(legacy_ctx)` — no silent drops.

### 6. Emit
`mapping_emitter.emit(...)`:
* Builds the manifest dict.
* Validates against `COLUMN_MAPPING_MANIFEST_SCHEMA`.
* Signs canonical JSON via ML-DSA-65.
* Writes `column-mapping.json` and `.sig` atomically (temp file + `fsync`
  + `os.replace`).
* Writes `.chainhash` for downstream linking.
