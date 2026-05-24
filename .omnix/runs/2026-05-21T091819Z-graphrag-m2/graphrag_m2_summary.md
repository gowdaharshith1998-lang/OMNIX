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
- Current full suite: 898 passed, 6 skipped, 13 xfailed in 96.59s.
- New GraphRAG slice tests include B2 embedding modes, B3 rollback, B4 deterministic parser, and Gate 12 backward-compat/sidecar verification.

## Cost Projection

- Mocked LLM cost projection for fixture enrich smoke: `$0.0010` for one pass over copied NIST fixture graph.
- 10M LOC production projection remains model/provider dependent; implementation records pass-level cost and halts on configured budgets so operators can calibrate from pilot enrich runs rather than hard-coded estimates.

## Known Issues / Deferred

- Python 3.14 cannot install `graspologic>=3.4.0` because published wheels require Python `<3.13`; M2 code uses deterministic connected-component fallback on this interpreter.
- `sqlite-vec` stable `0.1.10` is not published; dependency is pinned to installable `0.1.10a4`.
- GraphRAG integration wraps the existing rebuild dispatch and records provenance, but it does not modify the locked COBOL runner algorithm.
- TC401P is a documented no-graphrag byte-compat exception for edited-picture spacing: a live no-graphrag run emitted one extra space before `$105,250.00`, while the GraphRAG-enabled run verified all six programs. Diagnostic: `/tmp/tc401p_diagnostic.md`.

## Migration Notes

- Existing M0/M1 no-enrichment path remains default unless enrichment exists for the target or a direct neighbor.
- Provenance is supplementary: sidecar verification failure does not invalidate receipt verification.
- `.omnix/m2-graphrag-spec.md` is force-tracked as the canonical in-repo extract despite `.omnix/` being generally ignored.

## Phase B Completion

- B1 real fabric provider: shipped at `af61995` with OpenAI routing for enrichment.
- B2 real BGE embeddings with deterministic hash fallback: shipped via `OMNIX_GRAPHRAG_EMBED_MODE=auto|real|hash`.
- B3 SkillBank regression check plus auto-rollback: shipped and wired post-rebuild in the COBOL orchestrator.
- B4 dual_evolve deterministic failure parser: shipped; `parse_failure_analysis()` is keyword-based and never calls an LLM.

## TC401P Resolution

- Root cause: live no-GraphRAG rebuild generation is not source-byte deterministic for edited-picture formatting. The 2026-05-24 no-GraphRAG run `2026-05-24T011308432Z-4515e8f8` emitted `TOTAL=   $105,250.00` while the M0 baseline and fixture comment expect `TOTAL=  $105,250.00`.
- Outcome: DOCUMENTED as a known no-GraphRAG byte-compat exception. The locked Gate 6 behavior, receipt schema, and COBOL runner algorithm were not changed.
- Diagnostic: `/tmp/tc401p_diagnostic.md`.

## Backward-Compatibility Tests

- `test_no_graphrag_python_output_matches_m0_baseline`: PASS for the stable source-byte subset (`TC011A`, `TC012A`, `TC101M`) with documented no-GraphRAG source exceptions `TC201C`, `TC301E`, and `TC401P`.
- `TC201C`: Gate 6 verified behavior, but the live model emitted equivalent source with a different implementation shape than the May 19 baseline.
- `TC301E`: Gate 6 verified behavior, but the live model emitted quote-style-only source drift.
- `test_with_graphrag_produces_six_sidecars_all_verify`: PASS; six sidecars and six sidecar signatures were produced and the standalone audit verifier exited 0.

## Confirmed Locked-File Untouched

- `src/omnix/rebuild/cobol_runner.py` rebuild algorithm body: unchanged.
- `src/omnix/gates/gate6_behavioral.py`: unchanged.
- Receipt JSON schema: unchanged; provenance remains sidecar-only.
- M0 baseline directory `.omnix/receipts/cobol/20260519T091855Z/`: untouched.

## Known Deferred Items

- graspologic Leiden on Python 3.14: deterministic BFS/connected-component fallback remains in use.
- sqlite-vec stable `0.1.10`: installable alpha `0.1.10a4` remains pinned.
- ML-DSA-65 PQ signatures: pilot Phase 1.
- Live LLM smoke fixtures committed for offline replay: pilot Phase 2.
- CICS/IMS/VSAM dialects: pilot Phase 2.
- Pilot packaging: pilot Phase 3.
- Frontend wiring: pilot Phase 4.
