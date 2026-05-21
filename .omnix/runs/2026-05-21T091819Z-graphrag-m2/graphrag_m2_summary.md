# OMNIX GraphRAG M2 Summary

## Shipped

- Added offline COBOL enrichment packages: signatures, logic, data flow, community summaries, cache, and mocked provider.
- Added retrieval packages: BM25, vector table fallback, deterministic graph walk, RRF, token packer, and hybrid entry point.
- Added bounded traversal packages: four tool dispatchers, confidence parsing, budget caps, and observe-then-navigate loop.
- Added provenance packages: canonical subgraph fingerprinting, Ed25519 sidecar signing, sidecar writer, and audit zip sidecar verification.
- Added evolving pattern-cache packages: skill bank, controller, hard-case buffer, designer, and dual-evolve co-refinement.
- Integrated CLI commands: `omnix cobol enrich`, `omnix cobol skills list`, `review`, `rollback`, and `modernize --graphrag-*` flags.
- Integrated orchestrator prompt wrapping and sidecar emission without changing receipt JSON schema or Gate 6 behavior.

## Tests

- Baseline collection observed before this slice: 853 tests.
- Current full suite: 878 passed, 7 skipped, 13 xfailed in 68.01s.
- New GraphRAG slice tests: 45 passed.

## Cost Projection

- Mocked LLM cost projection for fixture enrich smoke: `$0.0010` for one pass over copied NIST fixture graph.
- 10M LOC production projection remains model/provider dependent; implementation records pass-level cost and halts on configured budgets so operators can calibrate from pilot enrich runs rather than hard-coded estimates.

## Known Issues / Deferred

- Python 3.14 cannot install `graspologic>=3.4.0` because published wheels require Python `<3.13`; M2 code uses deterministic connected-component fallback on this interpreter.
- `sqlite-vec` stable `0.1.10` is not published; dependency is pinned to installable `0.1.10a4`.
- GraphRAG integration wraps the existing rebuild dispatch and records provenance, but it does not modify the locked COBOL runner algorithm.

## Migration Notes

- Existing M0/M1 no-enrichment path remains default unless enrichment exists for the target or a direct neighbor.
- Provenance is supplementary: sidecar verification failure does not invalidate receipt verification.
- `.omnix/m2-graphrag-spec.md` is force-tracked as the canonical in-repo extract despite `.omnix/` being generally ignored.
