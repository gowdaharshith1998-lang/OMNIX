# OMNIX Repo Organization Execution

- Gate: Gate 4: Organization Plan
- Status: complete
- Written: 2026-06-08T17:47:53-07:00

## Notes

## Organization Plan and Execution

User approved continuing through gates without pausing. For safety, this Gate 4 pass avoids file moves because the worktree is already dirty and several internal docs may be referenced by tests or historical processes.

## Executed Low-Risk Organization Improvements

Created navigation and GitHub metadata files:

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

## Deferred Move Candidates

Do not move these until a dedicated reference-update batch exists:

- `NOTES.md` because tests reference it.
- `AUDIT.md`, `DESIGN.md`, `TODOS.md`, `slice21_recon.md`, `slices/`, and `.cursor/plans/canvas2d-renderer.md` because they need internal/archive decisions.
- `deploy/helm/omnix`, `services/github-app`, and `src/omnix/studio/frontend` because CI and Docker paths reference them.
- `src/web/graph_data_axiom_v2.json` because frontend code/tests reference it.

## Verification Planned

- Confirm new metadata files exist.
- Check issue-template YAML is syntactically readable where possible.
- Search for stale docs references that remain.
