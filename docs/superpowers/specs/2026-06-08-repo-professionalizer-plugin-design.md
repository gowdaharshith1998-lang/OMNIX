# Repo Professionalizer Plugin Design

Date: 2026-06-08
Repo context: `gowdaharshith1998-lang/OMNIX`
Plugin name: `repo-professionalizer`

## Purpose

Build a reusable Codex plugin that can connect to a GitHub-backed repository, audit it, reorganize it professionally, clean README and phase documentation, execute safe code refactors, verify changes, and prepare polished GitHub commits and pull requests.

The first target is OMNIX. The plugin should understand OMNIX's current shape, but it should not hardcode OMNIX so deeply that it cannot later run on other repositories.

## Scope

Version 1 includes:

- A gated multi-agent workflow for repository cleanup.
- Skills for audit, documentation cleanup, organization planning, refactor execution, and GitHub finishing.
- Scripts for deterministic repo inventory, docs inventory, and gate artifact creation.
- Templates for audit reports, docs plans, refactor plans, approval summaries, and PR descriptions.
- A personal marketplace-backed Codex plugin scaffold.

Version 1 does not include a production MCP server. The plugin structure should leave room for future MCP tools such as `scan_repo`, `generate_doc_inventory`, `rank_refactor_targets`, and `prepare_pr_summary`.

## Architecture

The plugin has three layers:

1. Skills layer
   Human-readable workflows that Codex can invoke. These define the review gates, agent roles, artifact expectations, and safety rules.

2. Scripts layer
   Deterministic helper scripts for repository inventory, documentation inventory, dirty worktree summaries, package/test detection, and gate artifact generation.

3. Future MCP layer
   An extension point for custom tools once the workflow has demonstrated value. MCP is intentionally deferred so the first version remains easy to inspect and iterate.

## Multi-Agent Model

The plugin uses a coordinator plus specialist worker agents.

- Coordinator Agent
  Owns scope, sequencing, review gates, integration, and final decisions.

- Repo Auditor Agent
  Scans structure, remotes, packages, docs, tests, CI, stale files, and risk areas.

- Docs Professionalizer Agent
  Cleans README files, service docs, phase descriptions, onboarding docs, and GitHub-facing copy.

- Architecture/Organization Agent
  Proposes file moves, docs hierarchy, naming cleanup, archive candidates, and repo navigation improvements.

- Code Refactor Agent
  Works only on approved batches. Focus areas include readability, duplication, module boundaries, typing, lint, tests, and maintainability.

- Verification Agent
  Runs targeted and broader checks, summarizes failures, and blocks completion when evidence is missing.

- GitHub Release Agent
  Prepares branch, staged files, commit slices, pull request description, checklist, and release notes.

Workers may investigate in parallel when their domains are independent. Edits are integrated by the coordinator and happen only in approved batches.

## Review Gates

The workflow uses hard review gates:

### Gate 0: Intake

Capture repository identity, current branch, remote URLs, dirty worktree state, language stacks, package managers, test commands, docs inventory, and GitHub state.

### Gate 1: Audit Report

Write a professional audit with risk-ranked sections covering docs, structure, code health, tests, security-sensitive areas, CI/GitHub polish, and quick wins.

### Gate 2: Docs Plan

Propose README and docs changes before editing. Include project positioning, setup, architecture, phases, service docs, and current capability language.

### Gate 3: Docs Execution

Apply approved documentation batches and produce a before/after summary.

### Gate 4: Organization Plan

Propose file moves, docs index changes, archive candidates, and naming cleanup. No files move without approval.

### Gate 5: Refactor Plan

Split code work into small subsystem/risk batches. Each batch must include expected files, intended behavior, risk, and verification commands.

### Gate 6: Refactor Execution

Apply one approved code batch at a time, run targeted tests, run broader tests when warranted, and stop with a concise summary.

### Gate 7: GitHub Finish

Prepare clean commits, branch/PR description, checklist, and release notes after all approved changes pass verification.

Each gate writes a markdown artifact under `.codex/repo-professionalizer/runs/<timestamp>/`.

## Plugin Contents

The v1 scaffold should include:

- `.codex-plugin/plugin.json`
- `skills/repo-professionalizer/SKILL.md`
- `skills/repo-audit/SKILL.md`
- `skills/docs-professionalizer/SKILL.md`
- `skills/repo-organization/SKILL.md`
- `skills/refactor-execute/SKILL.md`
- `skills/github-finish/SKILL.md`
- `scripts/repo_inventory.py`
- `scripts/docs_inventory.py`
- `scripts/write_gate_artifact.py`
- `assets/templates/audit-report.md`
- `assets/templates/docs-plan.md`
- `assets/templates/refactor-plan.md`
- `assets/templates/gate-summary.md`
- `assets/templates/pr-description.md`

The plugin should be created in the personal plugin directory and added to the personal Codex marketplace.

## Safety Rules

- Never overwrite uncommitted user work.
- Always report dirty worktree state during intake.
- Stage only explicitly approved files.
- Commit in reviewable slices.
- Do not move files before the organization plan is approved.
- Do not run broad refactors before the refactor plan is approved.
- Treat security-sensitive changes as high risk and require targeted tests.
- Stop when verification fails and summarize the root cause instead of continuing.

## OMNIX Profile

The first version should recognize OMNIX-specific areas:

- Python package under `src/omnix`.
- Python tests under `tests`.
- Node GitHub app under `services/github-app`.
- Additional service docs under `services/*/README.md`.
- Main documentation under `docs`.
- Data migration documentation under `docs/dm`.
- Deployment assets under `deploy`.
- Studio frontend under `src/omnix/studio/frontend`.
- Existing phase/slice history under `docs/screenshots/slice-history` and related docs.

This profile is guidance for the first run, not a permanent limitation.

## Verification

Before handing back the scaffolded plugin:

- Validate the plugin manifest with the plugin creator validator.
- Confirm no placeholder text remains in manifests or core skill files.
- Confirm the marketplace entry includes installation policy, authentication policy, and category.
- Confirm scripts run with `--help` or a dry-run mode where practical.

## Success Criteria

The plugin is successful when a user can invoke it to:

- Understand the current repository state.
- Receive a professional cleanup plan.
- Review documentation changes before they are applied.
- Review organization changes before files move.
- Review code refactor batches before implementation.
- See verification evidence for every applied batch.
- Finish with clean commits and a professional pull request description.
