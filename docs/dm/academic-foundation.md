# Academic Foundation

OMNIX-DM is built on the Wang / Dillig UT Austin trilogy. Three peer-reviewed
papers inform three implementation areas: mapping, synthesis, and formal
verification.

## Mediator (POPL 2018)

> *Verifying Equivalence of Database-Driven Applications*  
> Wang, Dillig, Lahiri, Cook — arXiv:1710.07660 — POPL 2018

* Verifies equivalence across schema versions of a database-driven app.
* Encoding: **theory of relational algebra with updates (TRA)** into Z3
  via list-theory mapping.
* Bisimulation invariants over TRA.
* 10,500 LOC Java. 20/21 benchmarks reported equivalent. 2-second SMT
  timeout per query.

**What D1-D2 use**: the `ColumnMapping` data structure carries a placeholder
for a future bisimulation invariant.

## Migrator (arXiv:1904.05498)

> *Synthesizing Database Programs for Schema Refactoring*  
> Wang, Dillig — arXiv:1904.05498

Three-stage decomposition:

1. **Guess value correspondence** — for each target column, propose source
   expressions.
2. **Sketch generation** — assemble candidate programs with holes.
3. **Enumerative search** — fill holes; prune by *minimum failing inputs*
   (MFI).

Push-button — no user input beyond source program + schemas.

**What D1 uses**: Stage 1 — value correspondence — is what the D1 semantic
matcher approximates, with LLM embeddings replacing manual guessing.

## Dynamite (PVLDB 2020)

> *Synthesizing Datalog Programs from Input-Output Examples*  
> Wang, Shah, Criswell, Pan, Dillig — arXiv:2003.01331 — PVLDB 2020

* Cross-model: relational ↔ document ↔ graph.
* 28 realistic scenarios.
* Datalog semantics drives efficient synthesis.

**What D1 uses**: cross-model awareness. D1's parser already handles
all four dialects (PG, MySQL, Oracle, MongoDB) at the data-structure
level. D3-D5 own the transformation synthesis and execution paths.

## Supporting layer

| Work | Relevance |
|---|---|
| SQLSolver (LIA* theory) | reports equivalence for 346 / 359 query pairs |
| Qed (PVLDB 2024) | 299 Calcite test-suite pairs |
| EQUITAS | SMT containment for SQL |
| EquiBench (Stanford, arXiv:2502.12466) | benchmark for SQL equivalence |
| LLM-SQL-Solver (arXiv:2312.10321) | LLM-assisted equivalence checking |
| Cheung (UC Berkeley EECS-2025-174) | LLM-based code translation needs formal compositional reasoning; bounded proofs feasible |

## Position in OMNIX-DM

The current implementation delivers the proposal, synthesis, and migration
execution layers. A Z3-backed formal verification layer remains future work.
These phases are necessary but not sufficient for any claim of complete
migration correctness. Stronger correctness claims require the formal layer and
environment-specific validation.

This is the documentation invariant: state the verified surface, then state the
remaining gap.
