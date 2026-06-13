# OMNIX Project Phases

This document separates shipped surfaces from active implementation tracks and
future milestones. The root `README.md` stays focused on quick evaluation; this
file gives reviewers a slightly deeper phase map.

## Completed Or Available

### Local Code Intelligence

Status: Available in v0.6.1

- Graph analysis CLI and localhost Studio.
- Universal Tree-sitter ingestion with packaged Python, TypeScript, Java, Go,
  Ruby, and Rust grammar wheels.
- Specialist Python and TypeScript parser passes for richer symbol extraction.
- Parser grammar visibility through `omnix grammar status` and
  `omnix grammar list`.

### Signed Finding Receipts

Status: Available in v0.6.1

- `omnix find-bugs <path> --emit-receipts` emits per-finding Ed25519 receipts.
- Scan manifests are signed with ML-DSA-65 over a Merkle root.
- `omnix axiom verify-scan` detects changed bytes, missing findings, and
  manifest tampering.
- `omnix axiom export-vault` produces an offline audit bundle.

### Repository Professionalization

Status: Available in this branch

- Public README, docs index, contribution guide, security policy, license, issue
  templates, pull request template, and changelog.
- CI coverage for Python, frontend, vault tests, cloud tests, GitHub App build,
  and Helm rendering.
- Dependency update configuration and CodeQL workflow.

## Active Implementation Tracks

### M1: Single-Node Java Rebuild

Status: Demo / active implementation

- Generates a per-node rebuild spec.
- Dispatches an LLM with dependency context.
- Runs gates 1-4 mechanically.
- Emits a signed rebuild receipt.
- See `docs/M1_DEMO.md` for the current demo path and known limitations.

### OMNIX-DM Data Migration

Status: Implemented in staged library surfaces

- D1: schema understanding and signed column mappings.
- D2: edge-case profiling and signed manifests.
- D3: transformation synthesis with halt receipts.
- D4: bulk import with batch and quarantine receipts.
- D5: PostgreSQL CDC sampling and cutover proposal artifacts.
- See `docs/dm/` for the phase runbooks and academic foundation.

### Cloud, GitHub App, And Deployment

Status: Private-pilot / enterprise surfaces

- FastAPI cloud API, tenant-aware job surfaces, and audit-kit export.
- GitHub App service for repository-facing automation.
- Helm, KOTS, Docker, and air-gapped deployment assets.
- These surfaces require project scoping and deployment decisions outside the
  public self-serve CLI path.

## Planned Milestones

| Milestone | Scope |
| --- | --- |
| M2 | Whole-module migration on a real OSS Java codebase with gates 5 and 6 producing property and behavioral evidence. |
| M3 | Engineer-review workspace with triage queue, side-by-side diffs, and keyboard-driven approve/rerun/edit flow. |
| M4 | Shadow bridge for production-traffic replay, signed request receipts, and divergence alerts. |
| M5 | Executive dashboard and regulator-facing audit explorer with PDF export. |

## Decision Log

| Date | Decision | Reason |
| --- | --- | --- |
| 2026-06-09 | Keep OMNIX source-available rather than open source. | The repo is public for evaluation, hiring review, and diligence, while commercial use still requires a license. |
| 2026-06-09 | Package the six advertised Tree-sitter grammar wheels as runtime dependencies. | Fresh installs should match the README and CI should exercise the parser surface without hidden local packages. |
| 2026-06-09 | Add CodeQL and Dependabot configuration. | Public professional repos should expose dependency and static-analysis posture, even when commercial features remain private-pilot scoped. |
