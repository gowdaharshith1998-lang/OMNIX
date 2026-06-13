# OMNIX-DM — Autonomous AI Data Migration

OMNIX-DM is the data-migration layer beneath the OMNIX code replicator. Its
outputs are signed, inspectable migration artifacts, not a claim of automatic
or mathematically proven migration correctness.

## D1-D5 status index

| Phase | Scope | Current label | Primary receipt |
|---|---|---|---|
| D1 Schema Understanding | Parse legacy and target schemas, extract metadata, propose column mappings with confidence and review flags. | Available as library APIs. | `column-mapping.json` |
| D2 Edge-Case Profiling | Plan and run edge-case probes for mapped columns, surfacing blockers and probe failures explicitly. | Available as library APIs. | `edge-case-manifest.json` |
| D3 Transformation Synthesis | Generate per-column transformer specs from D1/D2 evidence, with property-derived checks and halt receipts when synthesis fails. | Present in current tree; package/release status should be stated separately. | `transformer-spec-*.json` or `transformer-halt-*.json` |
| D4 Bulk Import | Apply transformer specs to every legacy row, write target batches, and quarantine failures. | Present in current tree; operator-run with target DDL preconditions. | `batch-receipt-*.json`, `quarantine-manifest.json` |
| D5 Change Data Capture | Replay PostgreSQL logical changes after D4, track lag, and emit operator-facing cutover proposals. | PostgreSQL path present; Oracle/MySQL adapters intentionally stubbed. | sampled CDC receipts, lag reports, cutover proposal |

These receipts create an auditable evidence chain. They do not establish
mathematical proof of migration correctness or guarantee regulatory compliance.

D1 and D2 emit ML-DSA-65 signed JSON manifests under
`.omnix/receipts/dm/pra-d1-d2/<migration_id>/`, chained by SHA-256
predecessor hash for tamper-evident audit. The directory name is historical;
the public product surface is D1-D5.

## Pipeline

```
legacy DDL  ─┐
             ├─► D1 parse  ─► metadata  ─► embed  ─► match  ─► column-mapping.json  (signed)
target DDL  ─┘                                                       │
                                                                     ▼
                                                            edge-case-manifest.json (signed,
                                                                     chained to D1)
```

## Evidence and explicit gaps

Every D1-D2 path that could otherwise fail silently surfaces explicitly:

| Where | What is surfaced |
|---|---|
| `ddl_parser.parse` | unrecognised statements → `ParseFailure` (not empty SchemaSpec) |
| `semantic_matcher.match` | low confidence / ambiguity / no_match → status fields + top-3 candidates |
| `probe_planner.plan` | every mapping probed *or* explicitly excluded with reason |
| `prober.run` | timeouts / errors → `status='timeout'/'error'` with reason |
| `manifest_emitter.emit` | sign-then-emit atomic — no half-written receipts |

## Academic foundation

Built on the Wang / Dillig (UT Austin) trilogy:

* **Mediator** (POPL 2018) — bisimulation invariants over relational
  algebra with updates (TRA), discharged in Z3. A Z3-backed formal layer remains
  future work.
* **Migrator** (arXiv:1904.05498) — value-correspondence Stage 1 plus sketch
  synthesis and MFI pruning. D3 implements the transformation-synthesis path.
* **Dynamite** (PVLDB 2020) — Datalog cross-model synthesis. D3-D5 use this as
  design input for transformation and migration execution.

The current implementation is the proposal, probe, and receipt layer. A
Z3-backed formal verification layer remains future work. The work sits in the
academic literature; OMNIX-DM is the engineering productisation.

## Files

* `src/omnix/dm/_types.py` — shared frozen dataclasses
* `src/omnix/dm/d1_schema_understanding/` — D1 pipeline
* `src/omnix/dm/d2_edge_case_profiling/` — D2 planner + probers
* `src/omnix/dm/receipts/` — JSON Schema + signing + Merkle chain
* `src/omnix/crypto/ml_dsa_65.py` — FIPS-204 ML-DSA-65 wrapper

## Operator runbook

See [`runbook.md`](runbook.md) for the CLI / driver invocations that
operators run against customer environments.
