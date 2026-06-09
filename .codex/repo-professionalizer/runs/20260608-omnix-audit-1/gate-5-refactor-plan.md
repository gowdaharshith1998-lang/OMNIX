# GitHub App Path Validation Refactor Plan

- Gate: Gate 5: Refactor Plan
- Status: approved
- Written: 2026-06-08T17:48:15-07:00

## Notes

## Refactor Batch: GitHub App target path validation

Files:

- `services/github-app/src/handlers/job_complete.ts`
- `services/github-app/tests/job_complete.test.ts`

## Current Problem

`validateTargetPath()` checked `.github/workflows` against the slash-normalized raw string, then returned a collapsed `parts.join("/")`. A path such as `.github//workflows/pwn.yml` bypassed the raw prefix check but collapsed to `.github/workflows/pwn.yml`, allowing a workflow file write despite the explicit block.

## Intended Behavior

- Reject `.github/workflows/*`.
- Reject collapsed workflow paths such as `.github//workflows/*`.
- Reject Windows separator variants such as `.github\\workflows\\*`.
- Continue accepting and collapsing normal paths such as `src//main/java/Foo.java`.

## Risk

Medium/high security-sensitive GitHub App behavior, but narrow function-level change.

## Verification Commands

- Focused red/green Node extraction check against actual `validateTargetPath` source.
- Full intended command when npm dependencies are available: `npm --prefix services/github-app test -- --runTestsByPath tests/job_complete.test.ts tests/pr_comment.test.ts`.
- Build intended command when npm dependencies are available: `npm --prefix services/github-app run build`.
