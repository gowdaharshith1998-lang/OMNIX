# OMNIX Professionalization Audit

- Gate: Gate 1: Audit Report
- Status: complete
- Written: 2026-06-08T17:29:36-07:00

## Notes

## Executive Summary

Gate 1 ran read-only intake and multi-agent audit against OMNIX. The repo is substantial and active: Python core, TypeScript GitHub App, React/Vite Studio frontend, Helm/deploy assets, service packages, and a broad docs tree. The main professionalism gap is not lack of material; it is coherence. Public docs, marketing docs, onboarding, DM docs, CI, and internal notes each tell a slightly different story about status, availability, proof/compliance claims, and how a new user should navigate the repo.

The safest cleanup path is docs/status normalization first, then GitHub/repo metadata, then organization proposals, then small code/security refactor batches.

## Audit Inputs

- Gate 0 inventory: `repo_inventory.py`, `docs_inventory.py`
- Multi-agent workers: docs audit, repo organization/GitHub polish audit, code health/verification audit
- Direct spot checks: `README.md`, `docs/dm/README.md`, `docs/onboarding/scanning.md`, `services/github-app/README.md`, `.github/workflows/*.yml`, `pyproject.toml`, package manifests, `services/github-app/src/handlers/job_complete.ts`

No docs, code, moves, staging, commits, or tests were performed in Gate 1.

## Repository Identity and Branch State

- Repo: `C:\Users\HG\Documents\omnix`
- Remote: `https://github.com/gowdaharshith1998-lang/OMNIX.git`
- Branch: `main`
- HEAD: `4e5dd1f`
- Worktree: dirty before this workflow started; all existing changes are user-owned and must be protected.

## Dirty Worktree Risk

Current user-owned changes include deleted `AGENTS.md` and `CLAUDE.md`, modified `NOTES.md`, staged repo-professionalizer design spec, untracked implementation plan, modified cloud/security/GitHub-app files, modified tests, new security-related tests, and a new PDF. Any cleanup or refactor must avoid broad staging and must review file ownership first.

The deleted `AGENTS.md` and `CLAUDE.md` matter because they likely contained repo-specific agent guardrails. Confirm whether to restore, replace, or intentionally remove them before refactor batches.

## Documentation Findings

### High: public status language is inconsistent

- `README.md` says `What works today (v0.6)` while `pyproject.toml` is `0.6.1` and `CHANGELOG.md` has large Unreleased DM PR B/C sections.
- `README.md` says spec generation/orchestration are not yet exposed, while `docs/M1_DEMO.md` documents an `omnix rebuild` M1 flow.
- Recommended fix: create one canonical public status matrix that separates shipped CLI, private-pilot/cloud surfaces, demos, and planned roadmap.

### High: proof/compliance claims conflict

- `README.md` is appropriately careful about not claiming mathematical proof or 100% accuracy.
- `docs/marketing/marketplace_listing.md` and `docs/marketing/landing.md` use stronger language such as proving behavioral equivalence and compliant-by-default.
- Recommended fix: normalize all public claims to the README's safer evidence/receipt language.

### High: onboarding presents unavailable or unclear surfaces as live paths

- `docs/onboarding/scanning.md` describes tarball upload, PAT clone, GitHub App, and Helm live-observation paths as selectable journeys.
- Marketplace and Helm repo references need availability labels: local now, private pilot, enterprise/airgap, or planned.

### High: OMNIX-DM index is stale relative to detailed phase docs

- `docs/dm/README.md` and `docs/dm/runbook.md` still frame the layer as PR A / D1-D2.
- `docs/dm/d3-transformation-synthesis.md`, `docs/dm/d4-bulk-import.md`, and `docs/dm/d5-change-data-capture.md` now exist and describe later phases.
- Recommended fix: update the DM README/runbook into a D1-D5 index with clear status per phase.

### Medium: service READMEs need a consistent template

- `services/github-app/README.md` leads with internal `Shape C` / `Shape A` terminology.
- `services/scientist-python/README.md`, `services/scientist-node/README.md`, and `services/scientist-java/README.md` are useful but thin: they need status, local build/test commands, integration role, and maintenance notes.

### Medium: internal history is too visible at top level

- Candidates for an internal/archive plan: `AUDIT.md`, `DESIGN.md`, `TODOS.md`, `slice21_recon.md`, `slices/`, `.cursor/plans/canvas2d-renderer.md`, `docs/XFAIL_AUDIT.md`, and the untracked PDF.
- Do not blindly move `NOTES.md`: tests reference it.

### Low/Medium: broken or missing docs references

- `docs/deploy/airgap.md` references `docs/compliance/`, but that directory is absent.
- There is no `docs/README.md`, `services/README.md`, `deploy/README.md`, or `scripts/README.md` to orient readers.

## GitHub and Repo Organization Findings

### High: GitHub-facing metadata is incomplete

- `.github` contains workflows only.
- Missing or intentionally absent files to decide: `.github/PULL_REQUEST_TEMPLATE.md`, `.github/ISSUE_TEMPLATE/*`, `.github/CODEOWNERS`, `CONTRIBUTING.md`, `SECURITY.md`, `CODE_OF_CONDUCT.md`, and `LICENSE`.
- `README.md` says All rights reserved, while `services/scientist-node/package.json` points to `LICENSE`. Licensing needs an explicit decision.

### Medium: CI exists but is under-surfaced

- `.github/workflows/ci.yml` and `.github/workflows/cloud-ci.yml` exist.
- README lacks badges or a concise CI matrix.
- `cloud-ci.yml` still includes branch `feat/deploy-shape-a-cloud`, which may be stale branch-specific polish debt.

### Medium: dependency install commands should be made reproducible

- `cloud-ci.yml` uses `npm install` for `services/github-app` and caches from package metadata.
- Professional CI usually prefers lockfile-backed `npm ci` where lockfiles exist.

### Medium: tracked runtime/generated artifacts need review

- `src/omnix/receipts/omnix.db-shm` and `src/omnix/receipts/omnix.db-wal` appear tracked while `.gitignore` ignores root DB sidecars.
- Review whether these are intentional fixtures or accidental runtime state.

### Organization move risks

High-risk anchors that should not move without reference updates and tests:

- `deploy/helm/omnix`: referenced by `cloud-ci.yml`, `deploy/build-airgap.sh`, and Helm chart paths.
- `services/github-app`: referenced by cloud CI.
- `src/omnix/studio/frontend`: referenced by CI and Dockerfile paths.
- `src/web/graph_data_axiom_v2.json`: looks generated but is referenced by Studio frontend tests/components.

## Code Health and Verification Findings

### High: GitHub App workflow-write block is bypassable

In `services/github-app/src/handlers/job_complete.ts`, `validateTargetPath()` checks `.github/workflows` against the raw slash-normalized string, then returns a collapsed `parts.join("/")`. A path like `.github//workflows/pwn.yml` does not match the raw prefix check but returns `.github/workflows/pwn.yml`, allowing a workflow write despite the explicit block.

Recommended batch: add a regression test in `services/github-app/tests/job_complete.test.ts` and validate against the collapsed path before returning.

### Medium: active security hardening deserves focused verification

Current dirty work includes security-sensitive areas:

- `src/omnix/cloud/ingest/git_clone.py`: URL allowlist and local/private-address protections.
- `src/omnix/cloud/auth/tenancy.py`: tenant trust now appears session-based rather than header-based.
- `src/omnix/studio/security.py` and `src/omnix/studio/server.py`: filesystem containment for Studio routes.
- `src/omnix/agents/tools.py`: agent tool security changes.

These should be handled as separate refactor/security batches, not mixed with docs cleanup.

## Likely Verification Commands

Use targeted commands by batch:

- Cloud/security Python batch: `python -m pytest -q tests/cloud/test_auth.py tests/cloud/test_cutover.py tests/cloud/test_git_clone.py tests/cloud/test_git_ingest_api.py tests/cloud/test_jobs_api.py tests/cloud/test_tus.py tests/studio/test_workspace_security.py tests/test_agents_tools_security.py`
- Python lint batch: `python -m ruff check src/omnix/agents/tools.py src/omnix/cloud src/omnix/studio/security.py src/omnix/studio/server.py tests/cloud tests/studio/test_workspace_security.py tests/test_agents_tools_security.py`
- GitHub App batch: `npm --prefix services/github-app test -- --runTestsByPath tests/job_complete.test.ts tests/pr_comment.test.ts`
- GitHub App build: `npm --prefix services/github-app run build`
- Studio metadata batch: `npm --prefix src/omnix/studio/frontend run typecheck`
- Full Python baseline: `pytest tests/ -q --tb=line`

Gate 1 did not run these test suites. No passing-test claim is made.

## Recommended Cleanup Sequence

1. Gate 2 Docs Plan: create a canonical public status matrix and approved docs batches.
2. Gate 3 Docs Execution: normalize README, DM docs, onboarding, marketing claims, and service README templates.
3. Gate 4 Organization Plan: propose docs index files, internal/archive destinations, GitHub metadata files, and generated/runtime artifact decisions.
4. Gate 5 Refactor Plan: define focused batches for GitHub App path validation, cloud tenant/auth, Studio filesystem containment, and git clone hardening.
5. Gate 6 Refactor Execution: execute one approved batch at a time with targeted tests.
6. Gate 7 GitHub Finish: stage approved files only, commit in slices, and prepare PR text with verification evidence.

## Work That Needs Approval Before Edits

- Whether Marketplace, Helm, hosted cloud, and GitHub App paths are live, private pilot, or planned.
- License model: keep All rights reserved, add a license file, or use a commercial/custom license notice.
- Security contact and disclosure policy.
- Restore, replace, or remove deleted `AGENTS.md` and `CLAUDE.md`.
- Whether to keep public `axiom` naming or shift docs toward receipts/provenance language.
- Which internal docs should remain public versus move to `docs/internal` or `docs/archive`.
- Whether to prioritize the GitHub App workflow-write fix before documentation cleanup.

## Gate 1 Decision

Gate 1 is complete. Recommended next step is Gate 2 Docs Plan, unless the user chooses to interrupt the sequence for the high-priority GitHub App path-validation fix.
