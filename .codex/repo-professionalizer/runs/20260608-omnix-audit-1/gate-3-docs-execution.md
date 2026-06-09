# OMNIX Documentation Cleanup Execution

- Gate: Gate 3: Docs Execution
- Status: complete
- Written: 2026-06-08T17:47:53-07:00

## Notes

## Completed Docs Batches

### Batch A: Public status and claims

Updated `README.md` with a `v0.6.1` project status matrix, clarified self-serve vs private-pilot surfaces, refreshed the OMNIX-DM D1-D5 summary, and changed M1/full orchestration wording to avoid contradictory status claims.

Updated `docs/marketing/marketplace_listing.md` and `docs/marketing/landing.md` to use signed evidence, receipt integrity, and audit-support language instead of proof/compliance guarantees.

### Batch B: DM phase docs

Updated `docs/dm/README.md` from PR A-only framing to a D1-D5 status index and renamed the honesty section to evidence/explicit gaps.

Updated `docs/dm/runbook.md` to clarify it documents D1-D2 operator Python invocation patterns, not a single supported `omnix dm migrate` CLI flow.

### Batch C: Onboarding labels

Updated `docs/onboarding/scanning.md` with availability labels and a safer compliance/evidence statement.

### Batch D: Service docs

Updated `services/github-app/README.md` to remove leading internal `Shape C` language, state deployment boundaries, and add verification commands.

## Changed Files

- `README.md`
- `docs/dm/README.md`
- `docs/dm/runbook.md`
- `docs/onboarding/scanning.md`
- `docs/marketing/marketplace_listing.md`
- `docs/marketing/landing.md`
- `services/github-app/README.md`

## Verification Planned

- Search for risky claim language and stale status references.
- Run docs inventory.
- Do not claim tests pass for docs-only edits.
