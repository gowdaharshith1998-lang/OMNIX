# GitHub App Path Validation Refactor Execution

- Gate: Gate 6: Refactor Execution
- Status: complete
- Written: 2026-06-08T17:48:15-07:00

## Notes

## Executed Batch: GitHub App target path validation

## Changed Files

- `services/github-app/tests/job_complete.test.ts`
- `services/github-app/src/handlers/job_complete.ts`

## Changes

- Added regression expectations for `.github//workflows/pwn.yml` and `.github\\workflows\\pwn.yml`.
- Changed `validateTargetPath()` to build `candidate = parts.join("/")`, check the workflow block against `candidate.toLowerCase()`, and return `candidate`.

## TDD Evidence

- RED focused check before implementation: `.github//workflows/pwn.yml` was accepted.
- GREEN focused check after implementation: direct, double-slash, and Windows-separator workflow paths were rejected; normal path collapse still returned `src/main/java/Foo.java`.

## Pending Full Verification

Full Jest/build verification depends on npm and service dependencies being available in the environment.
