# OMNIX Agentic + Evolving GraphRAG M2 Spec

This file is the in-repo extract of the local dispatch:
`/home/harsh/Downloads/omnix_agentic_graphrag_godmode_mega_dispatch_v2.html`.

## Layers

1. Multi-pass enrichment: signatures, logic, data flow, communities.
2. Hybrid retrieval: BM25, vector, deterministic graph walk, RRF fusion, token packing.
3. Bounded agentic traversal: single observe-then-navigate loop with exactly four graph tools.
4. Provenance sidecar: supplementary JSON plus detached Ed25519 signature, never receipt schema fields.
5. Pattern cache evolution: hard-case buffer, skill bank, designer, rollback.
6. Dual-evolving co-refinement: Reflexion failure analysis refines query and subgraph within budget.

## Locked Decisions

- Embedding: `BAAI/bge-small-en-v1.5`.
- Vector: `sqlite-vec`.
- Sparse retrieval: `bm25s`.
- Community detection: `graspologic`.
- Token estimation: `tiktoken` `cl100k_base`.
- Receipt schema is locked; provenance is sidecar-only.
- No Neo4j, external vector DB, RL training, or frontend scope.
- Existing COBOL runner and Gate 6 behavior remain locked.

## EARS Summary

- `omnix cobol enrich <codebase_root>` enriches COBOL program/paragraph nodes incrementally by source SHA.
- Retrieval degrades gracefully when enrichment is absent.
- Agent traversal exposes `query_graph`, `expand_node`, `summarize_subgraph`, and `inspect_data_item`.
- Sidecars include subgraph fingerprint, retrieval mode counts, traversal path, applied skills, enrichment hash, token cost, and schema version `omnix.provenance.v1`.
- Skill-bank entries are bi-temporal and can be invalidated on regression.
- A fresh checkout with no enrichment must preserve M0 modernization behavior.
