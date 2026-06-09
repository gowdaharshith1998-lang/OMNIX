# OMNIX Documentation Cleanup Plan

- Gate: Gate 2: Docs Plan
- Status: approved
- Written: 2026-06-08T17:40:34-07:00

## Notes

## Goal

Normalize OMNIX's public repository presentation so README, DM docs, onboarding, marketing drafts, service docs, and GitHub metadata tell one accurate story.

## Approved Docs Batches

### Batch A: Public status and claims

Files:

- `README.md`
- `docs/marketing/marketplace_listing.md`
- `docs/marketing/landing.md`

Purpose:

- Update version/status wording from `v0.6` to `v0.6.1` where appropriate.
- Add a canonical capability/status matrix.
- Normalize proof/compliance wording to evidence, auditability, and review suitability.
- Remove or soften unsupported claims like guaranteed proof of equivalence or compliant-by-default.

Risk: Medium. These are GitHub-facing product claims.

### Batch B: DM phase documentation

Files:

- `docs/dm/README.md`
- `docs/dm/runbook.md`

Purpose:

- Replace PR A-only framing with a D1-D5 phase index.
- Mark D1-D2 as implemented library surfaces and D3-D5 as documented/active implementation phases unless verified otherwise.
- Preserve honest gaps and formal-proof deferral.

Risk: Medium. Phase/status language affects roadmap trust.

### Batch C: Onboarding availability labels

Files:

- `docs/onboarding/scanning.md`

Purpose:

- Label local evaluation, hosted/cloud pilot, GitHub App, and enterprise/airgap paths by availability.
- Keep commands as examples, not guaranteed public production endpoints.

Risk: Medium. Prevents readers from assuming unavailable hosted surfaces are live.

### Batch D: Repo navigation and GitHub metadata

Files to create:

- `docs/README.md`
- `services/README.md`
- `deploy/README.md`
- `scripts/README.md`
- `CONTRIBUTING.md`
- `SECURITY.md`
- `.github/PULL_REQUEST_TEMPLATE.md`
- `.github/ISSUE_TEMPLATE/config.yml`
- `.github/ISSUE_TEMPLATE/bug_report.yml`
- `.github/ISSUE_TEMPLATE/docs_cleanup.yml`

Purpose:

- Add top-level navigation and contribution/security expectations.
- Keep licensing language commercial/all-rights-reserved; do not add an OSS license.

Risk: Low/Medium. New docs only, no code behavior.

## Deferred Organization Work

No file moves in Gate 3. Archive/internal moves need a separate Gate 4 execution plan because several internal docs are referenced by tests or may be useful historical records.

## Verification

- Search for remaining risky wording in edited docs: `prove`, `proof`, `compliant-by-default`, `100%`, stale `v0.6` references.
- Run markdown/path spot checks with `rg`.
- Do not claim test pass for docs-only changes.

## Approval State

User requested continuing full workflow without stopping; proceed through these batches while preserving existing user-owned dirty work.
