# OMNIX-DM D1-D2 Operator Runbook

> Status: this runbook documents operator Python invocation patterns for D1-D2.
> It is not a single supported `omnix dm migrate` CLI flow. D3-D5 have separate
> package-level docs and should be labeled by release status before customer use.
> Signed manifests provide receipt integrity, traceability, and review evidence;
> they are not a mathematical proof of correctness.

## D1 — Schema understanding

```python
from omnix.crypto import ml_dsa_65
from omnix.dm.d1_schema_understanding import (
    column_metadata, ddl_parser, mapping_emitter, semantic_matcher,
)

legacy = ddl_parser.parse(open("legacy.sql").read(), "oracle")
target = ddl_parser.parse(open("target.sql").read(), "postgres")

legacy_ctx = column_metadata.extract(legacy, legacy_readonly_conn)
target_ctx = column_metadata.extract(target, target_readonly_conn)

mappings = semantic_matcher.match(legacy_ctx, target_ctx)

pk, sk = ml_dsa_65.keypair()   # in practice, load from key vault
mapping_path = mapping_emitter.emit(
    mappings=mappings,
    legacy=legacy,
    target=target,
    migration_id="acme-corp-2026-05-26",
    secret_key=sk,
    public_key=pk,
    output_root=".omnix/receipts/dm/pra-d1-d2",
)
```

Inspect mappings that need operator attention:

```bash
jq '.mappings[] | select(.status != "ok")' \
  .omnix/receipts/dm/pra-d1-d2/acme-corp-2026-05-26/column-mapping.json
```

## D2 — Edge-case profiling

```python
from pathlib import Path
from omnix.dm.d2_edge_case_profiling import probe_planner
from omnix.dm.d2_edge_case_profiling.manifest_emitter import emit as emit_d2
from omnix.dm.d2_edge_case_profiling.probers import (
    null_distribution, encoding_anomaly, orphan_fk,
    timezone_drift, precision_boundary, sentinel_value,
)

plan = probe_planner.plan(mappings, legacy, max_total_cost_ms=30_000, seed=0)

probers = {
    "null_distribution": null_distribution.run,
    "encoding_anomaly":  encoding_anomaly.run,
    "orphan_fk":         orphan_fk.run,
    "timezone_drift":    timezone_drift.run,
    "precision_boundary": precision_boundary.run,
    "sentinel_value":    sentinel_value.run,
}

# Resolve table/column-spec lookups from legacy SchemaSpec for column_spec=...
def find_column(table, column):
    for t in legacy.tables:
        if t.name == table:
            for c in t.columns:
                if c.name == column:
                    return c
    return None

results = []
for req in plan.requests:
    runner = probers[req.category]
    if req.category == "orphan_fk":
        fk = next(
            (fk for t in legacy.tables
             for fk in t.foreign_keys
             if fk.from_table == req.legacy_table
             and fk.from_columns[0] == req.legacy_column),
            None,
        )
        results.append(runner(req, legacy_readonly_conn, fk_spec=fk))
    else:
        results.append(runner(
            req, legacy_readonly_conn,
            column_spec=find_column(req.legacy_table, req.legacy_column),
        ))

chain_hash = Path(mapping_path.parent / "column-mapping.chainhash").read_text().strip()
d2_path = emit_d2(
    results=tuple(results),
    migration_id="acme-corp-2026-05-26",
    predecessor_hash=chain_hash,
    secret_key=sk,
    public_key=pk,
    output_root=".omnix/receipts/dm/pra-d1-d2",
)
```

Inspect findings that block the migration:

```bash
jq '.findings[] | select(.severity == "blocker")' \
  .omnix/receipts/dm/pra-d1-d2/acme-corp-2026-05-26/edge-case-manifest.json
```

## Verifying receipt integrity

This verifies canonical bytes and signature integrity. It does not by itself
certify that a migration is correct or compliant.

```python
import json
from omnix.dm.receipts.ml_dsa_65_signer import verify_canonical
from omnix.crypto import ml_dsa_65

body = json.loads(open(receipt_path).read())
sig  = open(str(receipt_path) + ".sig").read().strip()
assert verify_canonical(body, sig, public_key=pk)
```

The chain hash file (`*.chainhash`) lets a verifier reproduce the
predecessor field for the next manifest in the chain — re-compute via
`omnix.dm.receipts.merkle_chain.next_hash` over the canonical bytes.
