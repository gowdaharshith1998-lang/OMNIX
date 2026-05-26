# OMNIX-DM — Autonomous AI Data Migration

OMNIX-DM is the data-migration layer beneath the OMNIX code replicator. **PR A**
delivers the first two phases of the platform:

* **D1 — AI Schema Understanding** — dialect-aware DDL parsing (Postgres /
  MySQL / Oracle / MongoDB) followed by semantic column matching with
  confidence scores.
* **D2 — AI Edge-Case Profiling** — pymdp-style expected-free-energy probe
  planning + six probers (NULL distribution, encoding anomaly, orphan FK,
  timezone drift, precision boundary, sentinel value).

Both phases emit ML-DSA-65 signed JSON manifests under
`.omnix/receipts/dm/pra-d1-d2/<migration_id>/`, chained by SHA-256
predecessor hash for tamper-evident audit.

## Pipeline

```
legacy DDL  ─┐
             ├─► D1 parse  ─► metadata  ─► embed  ─► match  ─► column-mapping.json  (signed)
target DDL  ─┘                                                       │
                                                                     ▼
                                                            edge-case-manifest.json (signed,
                                                                     chained to D1)
```

## Codex honesty

Every silent-drop path in PR A surfaces explicitly:

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
  algebra with updates (TRA), discharged in Z3. *Lands in PR E.*
* **Migrator** (arXiv 1904.05498) — value-correspondence Stage 1 +
  sketch synthesis + MFI pruning. *Lands in PR B (D3).*
* **Dynamite** (PVLDB 2020) — Datalog cross-model synthesis. *Lands in
  PR B / PR C.*

PR A is the AI proposal layer. PR E is the formal proof layer. Together
they form the productisation of the trilogy — the work sits in the academic
literature; OMNIX-DM is the engineering productisation.

## Files

* `src/omnix/dm/_types.py` — shared frozen dataclasses
* `src/omnix/dm/d1_schema_understanding/` — D1 pipeline
* `src/omnix/dm/d2_edge_case_profiling/` — D2 planner + probers
* `src/omnix/dm/receipts/` — JSON Schema + signing + Merkle chain
* `src/omnix/crypto/ml_dsa_65.py` — FIPS-204 ML-DSA-65 wrapper

## Operator runbook

See [`runbook.md`](runbook.md) for the CLI / driver invocations that
operators run against customer environments.
