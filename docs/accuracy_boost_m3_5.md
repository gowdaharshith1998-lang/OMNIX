# OMNIX Accuracy Boost M3.5

M3.5 adds an opt-in accuracy layer over the COBOL GraphRAG M2 path. The default path remains unchanged: no environment variables and no `--accuracy-boost` flag leave chunking, reranking, MCTS, and ESE/Cas disabled.

| Technique | Layer | Source | Control | Default |
| --- | --- | --- | --- | --- |
| cAST-style structural chunking | L2 retrieval | Zhang et al., cAST, EMNLP 2025, arXiv:2506.15655 | `OMNIX_CHUNK_MODE=auto|ast|line` | unset, node-level indexing |
| bge-reranker-v2-m3 cross-encoder | L2.5 retrieval | BAAI FlagEmbedding reranker pattern | `OMNIX_GRAPHRAG_RERANK_MODE=off|auto|on` | `off` |
| Thought-level MCTS | L3/L6 retry refinement | Li et al., RethinkMCTS, arXiv:2409.09584 | `OMNIX_MCTS_MODE=off|auto|on`, `OMNIX_MCTS_BUDGET` | `off`, budget `8` |
| Ensemble Semantic Entropy + Cas | L6 retry verifier telemetry | Ensemble-Based Uncertainty Estimation, arXiv:2603.27098 | `OMNIX_ESE_MODE=off|auto|on`, `OMNIX_ESE_THRESHOLD` | `off`, threshold `0.6` |

## How To Enable

```bash
omnix cobol modernize tests/fixtures/cobol/nist --target python --accuracy-boost
```

The flag sets `OMNIX_CHUNK_MODE=auto`, `OMNIX_GRAPHRAG_RERANK_MODE=auto`, `OMNIX_MCTS_MODE=auto`, and `OMNIX_ESE_MODE=auto` for the duration of that run only, then restores the previous environment.

## Smoke Results

NIST smoke comparison from `.omnix/runs/2026-05-24T022628762Z-472903d2/accuracy_boost_smoke_comparison.md`:

| Metric | Baseline | Accuracy-Boost |
| --- | ---: | ---: |
| modernize exit code | 1 | 0 |
| verified | 5 | 6 |
| gate6_failed | 1 | 0 |
| errored | 0 | 0 |
| wall clock seconds | 35 | 21 |
| total cost USD | 0.0 | 0.0 |
| rerank invocations | n/a | 6 |
| mcts invocations | n/a | 0 |
| ese escalations | n/a | 0 |

Both runs used mock enrichment. The boost run used `HF_HUB_OFFLINE=1` and `TRANSFORMERS_OFFLINE=1`; `bge-reranker-v2-m3` was not cached locally, so auto reranking exercised the fallback path.

## What It Costs

The smoke run recorded `$0.0` spend in run state for both baseline and boost. In live runs, `OMNIX_GRAPHRAG_RERANK_MODE=auto` may load a local Hugging Face cross-encoder if cached or reachable, and `OMNIX_MCTS_MODE=auto` / `OMNIX_ESE_MODE=auto` can add retry-time work only after a first-pass Gate 6 failure.

## Deferred

M3.5 does not include GEPA prompt evolution, SMT/Z3 equivalence checking, custom code-embedding fine-tuning, or AdverMCTS adversarial test generation. Those need labeled failure data or new solver dependencies and remain Phase 2 candidates.

## Locked Architecture Compliance

The implementation does not modify `src/omnix/rebuild/cobol_runner.py`, `src/omnix/gates/gate6_behavioral.py`, the receipt JSON schema, `.omnix/receipts/cobol/20260519T091855Z/`, or the YC demo run. Accuracy-boost behavior is additive around retrieval, retry guidance, and run telemetry.
