"""OMNIX-DM — Autonomous AI data migration platform.

PR A delivers the first two phases:
  * D1 — AI Schema Understanding (dialect-aware DDL → semantic column mapping)
  * D2 — AI Edge-Case Profiling   (active-inference probe planner + 6 probers)

Both phases emit ML-DSA-65 signed JSON manifests under
``.omnix/receipts/dm/pra-d1-d2/<migration_id>/``.

Academic foundation: Wang/Dillig UT Austin trilogy
  * Mediator   (POPL 2018)   — bisimulation over TRA in Z3 (lands in PR E)
  * Migrator   (arXiv 1904.05498) — value correspondence + sketch + MFI (PR B)
  * Dynamite   (PVLDB 2020)  — Datalog cross-model synthesis (PR B / PR C)

PR A is the AI proposal layer; the formal proof layer lands in PR E.
"""

__version__ = "0.1.0-dm-pra"

__all__ = ["__version__"]
