# OMNIX Repo Intake

- Gate: Gate 0: Intake
- Status: complete
- Written: 2026-06-08T17:24:29-07:00

## Notes

## Repository Identity

- Repo path: `C:\Users\HG\Documents\omnix`
- Remote: `https://github.com/gowdaharshith1998-lang/OMNIX.git`
- Branch: `main`
- HEAD: `4e5dd1f`
- Status: `main...origin/main`

## Dirty Worktree Guardrail

The worktree is already dirty and must be treated as user-owned state. Gate 2+ work must not overwrite or stage unrelated changes.

Current notable changes:

- Deleted: `AGENTS.md`, `CLAUDE.md`
- Modified docs: `NOTES.md`
- Staged new doc: `docs/superpowers/specs/2026-06-08-repo-professionalizer-plugin-design.md`
- Untracked plan: `docs/superpowers/plans/2026-06-08-repo-professionalizer-plugin.md`
- Modified GitHub app files: `services/github-app/src/handlers/job_complete.ts`, `services/github-app/src/handlers/pr_comment.ts`, `services/github-app/tests/pr_comment.test.ts`
- Modified cloud/security-adjacent Python files under `src/omnix/cloud/**`, `src/omnix/agents/tools.py`, and `src/omnix/studio/server.py`
- Modified tests under `tests/cloud/**`
- Untracked security/test files: `services/github-app/tests/job_complete.test.ts`, `src/omnix/studio/security.py`, `tests/studio/test_workspace_security.py`, `tests/test_agents_tools_security.py`
- Untracked PDF: `omnix-newly-added-files-full-contents.pdf`

## Inventory Summary

- Scanned files: 1,014
- Documentation/readme-like files: 45
- README files: 10
- Top-level directories: `.cursor`, `.github`, `benchmarks`, `demos`, `deploy`, `docs`, `scripts`, `services`, `slices`, `src`, `tests`

## Language Signals

- Python: 599 files
- TypeScript: 180 files
- YAML: 48 files
- Markdown: 44 files
- JSON: 44 files
- JavaScript: 24 files
- Java: 7 files
- Rust: 1 file
- TOML: 2 files

## Package and Build Signals

- Python: `pyproject.toml`, `requirements.txt`, `services/scientist-python/pyproject.toml`
- Node/frontend: root `package.json`, `src/omnix/studio/frontend/package.json`
- GitHub app: `services/github-app/package.json`
- Java service: `services/scientist-java/pom.xml`
- CI workflows: `.github/workflows/ci.yml`, `.github/workflows/cloud-ci.yml`

## Likely Verification Commands

From config and CI:

- Python: `pytest tests/ -q --tb=line`, `ruff check .`, `mypy src/omnix --ignore-missing-imports`
- Cloud: `python -m pytest tests/cloud/ -q --tb=short`
- Studio frontend: from `src/omnix/studio/frontend`, `npm test -- --run`, `npx tsc --noEmit`
- Root vault tests: `npm test`
- GitHub app: from `services/github-app`, `npm run build`, `npm test`, `npm run lint`
- Helm: `helm lint deploy/helm/omnix`, `helm template omnix deploy/helm/omnix`

## Gate 0 Decision

Proceed to Gate 1 audit only. Do not edit docs, move files, refactor code, stage files, or commit until later gates are approved.
