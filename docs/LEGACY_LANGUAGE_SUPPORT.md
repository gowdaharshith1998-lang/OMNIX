# Legacy and systems languages (quality + grammars)

OMNIX scores COBOL, IBM HLASM, and Fortran with **synthetic-stat** Python profiles
(`src/parser/quality_profiles/*.py`) so quality works even before full ingest wiring.
Parse failure remains at **parse/grammar** time, not at profile load. Real-codebase
calibration happens during Compliance Vault and customer onboarding — not with the
synthetic JSON fixtures in this repository.

## Supported today

**COBOL**

- **Tree-sitter:** [yutaro-sakamoto/tree-sitter-cobol](https://github.com/yutaro-sakamoto/tree-sitter-cobol)
- **Install:** clone the repository and build the `tree_sitter` language as described
  in the upstream `README` and `binding.gyp` (many deployments use a git submodule
  plus a small Python loader). PyPI name availability varies; prefer `git+https`
  against the exact release tag your platform pins.
- **Profile:** `cobol.py` — `score(stats)`; calibration sanity: **1.0** on the
  `cobol_substantial_stats.json` synthetic fixture (see `tests/parser/quality_profiles/fixtures/`).
- **Limitations:** **COBOL85**-oriented expectation; modern dialects and
  preprocessed copybooks are untested at scale.

**HLASM (IBM assembler)**

- **Tree-sitter:** [janus-llm/tree-sitter-ibmhlasm](https://github.com/janus-llm/tree-sitter-ibmhlasm)
- **Install:** build from the grammar repo; HLASM is rarely on PyPI as a single
  one-liner — use upstream build instructions and pin the same commit in CI and on
  customer z/OS-adjacent runners.
- **Profile:** `hlasm.py` — **1.0** on `hlasm_substantial_stats.json` fixture.
- **Limitations:** **Macro definitions and conditional assembly** are only
  partially representable; listing assembly may miss implicit USING ranges.

**Fortran**

- **Tree-sitter:** [stadelmanma/tree-sitter-fortran](https://github.com/stadelmanma/tree-sitter-fortran)
- **Install:** `python -m pip install git+https://github.com/stadelmanma/tree-sitter-fortran.git`
  (when published bindings match your tree_sitter / Python; otherwise build from
  the repo with the generator’s `bindings/python` flow).
- **Profile:** `fortran.py` — **1.0** on `fortran_substantial_stats.json` fixture;
  the grammar is roughly **~50% language coverage** — good for many scientific code
  paths, weak on exotic vendor extensions and heavy preprocessor use.
- **Limitations:** C preprocessor, `INCLUDE`, and some 2003+ / coarray features are
  not fully modeled; treat scores as heuristics, not a formal semantics guarantee.

**Fixture score summary (synthetic, non-exhaustive):** COBOL substantial **1.0**;
HLASM substantial **1.0**; Fortran substantial **1.0**. Minimal and stub fixtures
in the same directory exercise 0.3–0.6 and &lt;0.3 ranges for regression tests only.

## Roadmap (Integration #15 — deferred languages)

These are **not** shipping in OMNIX as supported grammars today. Do **not** describe
any of them as “supported in product” in marketing or documentation outside this
**Roadmap (Integration #15** section.

**RPG (IBM ILE / fixed-form legacy)**

- **Context:** **IBM “Project Bob”** is driving modernization toward March 2026 and
  beyond; more AI-assist and migration tooling is landing on the IBM roadmap. RPG
  demand is high in financial and manufacturing estates.
- **Grammar status for OMNIX:** **none** bound in the tree today (Community
  tree-sitter work exists but is not integrated).
- **Effort:** expect **multi-week** calendar time to add grammar load, test corpus,
  receipts, and quality handoff — a full “Integration #15”-style workstream, not a
  weekend task.

**PL/I**

- **Context:** mainframe estates still use PL/I for long-lived batch; modernization
  vendors and IBM are nudging customers toward API extraction and strangled
  replacement, which increases the value of a stable parse graph.
- **Grammar status:** **partial** public grammars, nothing merged into OMNIX; legal
  and long-tail dialect variance is high.
- **Effort:** **multi-week** to evaluate grammar candidates, add regression corpora
  (often customer-specific), and align receipts.

**JCL (Job Control Language)**

- **Context:** Every z/OS job still flows through JCL; it is a prerequisite to
  understanding batch topology even when applications are in COBOL, HLASM, or
  other languages. AI-assisted ops tooling increasingly references JCL in context
  windows.
- **Grammar status:** **partials / ad hoc** lexers in the wild; a robust
  open-source JCL tree-sitter with broad vendor coverage is **not** standard.
- **Effort:** **multi-week**; likely starts with a thin lexer and grows into
  statement-level parsing with MVS/ESA vs z/OS dialect toggles.

**Visual Basic 6 (VB6)**

- **Context:** 2020s rewrites and “VB6 in maintenance mode forever” both drive
  need for high-quality structural maps before LLM porting. Community interest in
  decompilation and recovery tooling remains steady.
- **Grammar status for OMNIX:** **none** integrated. Historical parsers and partial
  ASTs exist, but a maintained tree-sitter is **not** first-class in this repo.
- **Effort:** **multi-week**; forms, `Declare`, and COM interop complicate a pure
  syntax pass — expect parallel UI metadata ingestion.

**Summary:** *RPG*, *PL/I*, *JCL*, and *VB6* appear here **only** as a documented
**roadmap (Integration #15**). OMNIX does **not** claim to parse or score them in
production on day one. Customer onboarding and Compliance Vault are the right time
to validate any future grammar integration.
