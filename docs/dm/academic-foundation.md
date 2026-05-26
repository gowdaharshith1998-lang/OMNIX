# Academic Foundation

OMNIX-DM is built on the Wang / Dillig UT Austin trilogy. Three peer-reviewed
papers, three load-bearing primitives, three target PRs.

## Mediator (POPL 2018)

> *Verifying Equivalence of Database-Driven Applications*  
> Wang, Dillig, Lahiri, Cook — arXiv:1710.07660 — POPL 2018

* Verifies equivalence across schema versions of a database-driven app.
* Encoding: **theory of relational algebra with updates (TRA)** into Z3
  via list-theory mapping.
* Bisimulation invariants over TRA.
* 10,500 LOC Java. 20/21 benchmarks proven equivalent. 2-second SMT
  timeout per query.

**What PR A pulls**: the `ColumnMapping` data structure carries a
placeholder for the bisimulation invariant that PR E will fill.

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

**What PR A pulls**: Stage 1 — value correspondence — is exactly what
the D1 semantic matcher does, with LLM embeddings replacing manual
guessing.

## Dynamite (PVLDB 2020)

> *Synthesizing Datalog Programs from Input-Output Examples*  
> Wang, Shah, Criswell, Pan, Dillig — arXiv:2003.01331 — PVLDB 2020

* Cross-model: relational ↔ document ↔ graph.
* 28 realistic scenarios.
* Datalog semantics drives efficient synthesis.

**What PR A pulls**: cross-model awareness. D1's parser already handles
all four dialects (PG, MySQL, Oracle, MongoDB) at the data-structure
level. PR B / PR C own the Datalog synthesis itself.

## Supporting layer

| Work | Relevance |
|---|---|
| SQLSolver (LIA* theory) | proves 346 / 359 query pairs equivalent |
| Qed (PVLDB 2024) | 299 Calcite test-suite pairs |
| EQUITAS | SMT containment for SQL |
| EquiBench (Stanford, arXiv:2502.12466) | benchmark for SQL equivalence |
| LLM-SQL-Solver (arXiv:2312.10321) | LLM-assisted equivalence checking |
| Cheung (UC Berkeley EECS-2025-174) | LLM-based code translation needs formal compositional reasoning; bounded proofs feasible |

## Position of PR A

PR A delivers the AI proposal layer. PR E delivers the formal proof layer
(Mediator's bisimulation invariants discharged in Z3). PR B delivers the
Datalog synthesis (Migrator + Dynamite combined). PR A is necessary but
not sufficient for the "100% perfect migration" claim — that claim is
discharged only after PR E ships.

This honesty is the Codex axiom in spec form.
