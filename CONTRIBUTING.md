# Contributing to OMNIX

Thanks for your interest in OMNIX. This guide explains how to set up the
project, how the codebase is organized, and how to get a change reviewed and
merged.

## Project scope and licensing

OMNIX is **source-available**, not OSI open source. It is distributed under a
custom evaluation license — see [LICENSE](LICENSE) before reusing any code
outside evaluation.

Contributions are welcome for evaluation, bug fixes, documentation, and
collaboration. By submitting a contribution, you agree that your contribution
is licensed to the project owner (Harshith Gowda) under the terms of
[LICENSE](LICENSE), and that you have the right to grant that license. Do not
contribute code you cannot license this way (for example, proprietary
third-party code, customer code, or generated credentials).

OMNIX is a hiring portfolio and a commercial prototype. It is not yet
production-ready for real migrations; please keep claims in code, tests, and
docs accurate and verifiable.

## Before you start

- Read the [Code of Conduct](CODE_OF_CONDUCT.md). It applies to issues, pull
  requests, and all project interaction surfaces.
- For where to ask questions, see [.github/SUPPORT.md](.github/SUPPORT.md).
- For anything security-sensitive, follow [SECURITY.md](SECURITY.md) and do not
  open a public issue.

## Monorepo map

OMNIX is a polyglot monorepo. The main areas are:

| Area | Path | Stack |
| --- | --- | --- |
| Python core | `src/omnix/` | Python 3.10+ (parser, graph, rebuild, verify, receipts, crypto, dm, cloud, fabric, find_bugs, axiom, scan) |
| CLI entry point | `src/omnix/cli.py` (console script `omnix`); root shim `omnix.py` | Python |
| React Studio frontend | `src/omnix/studio/frontend/` | TypeScript, Vite, Vitest |
| Node services | `services/` | Node.js (`github-app`, `scientist-node`, and language scientists) |
| Provider-key vault | `tests/vault/` and supporting JS | Node.js |
| Tests | `tests/` (Python), `tests/vault/` (vault), `src/omnix/studio/frontend/` (frontend) | mixed |

A local development stack (Postgres, Redis, and supporting services) is defined
in [docker-compose.dev.yml](docker-compose.dev.yml):

```bash
docker compose -f docker-compose.dev.yml up
```

## Development setup

Python:

```bash
pip install -e ".[dev,cloud]"
```

Frontend:

```bash
cd src/omnix/studio/frontend
npm ci
```

Vault / Node tooling at the repo root:

```bash
npm ci
```

## Run these to match CI

CI runs four jobs (see
[.github/workflows/ci.yml](.github/workflows/ci.yml)). Run the matching
commands locally before opening a pull request.

**1. Python tests**

```bash
pip install -e ".[dev,cloud]"
pytest tests/ -q --tb=line
```

**2. Python lint and types**

```bash
pip install ruff mypy
ruff check .
pip install -e .
mypy src/omnix --ignore-missing-imports
```

**3. Frontend tests** (run from `src/omnix/studio/frontend`)

```bash
cd src/omnix/studio/frontend
npm ci
npm test -- --run
npx tsc --noEmit
```

**4. Vault tests** (run from the repo root)

```bash
npm ci
npm test -- tests/vault
```

> Note: the Python test job also installs a JDK (Temurin 21) because some
> verification paths shell out to the JVM. If you touch those paths, make sure a
> Java 21 runtime is on your `PATH`.

## Code style

- **Python** is formatted and linted with **ruff** and type-checked with
  **mypy**. Both are configured in [pyproject.toml](pyproject.toml)
  (`[tool.ruff]` and `[tool.mypy]`). The lint baseline is intentionally
  permissive and ratcheted up over time — match the existing configuration
  rather than introducing new ignores. Line length is 100.
- New Python modules are type-checked by mypy. Some legacy modules are still on
  the `[tool.mypy.overrides]` ignore list; do not add new modules to that list,
  and pay down type debt where you can.
- **TypeScript / frontend** must pass `npx tsc --noEmit` and the Vitest suite.
- Keep changes focused. Include tests for behavior changes. Call out
  security-sensitive paths explicitly in the PR description (see
  [SECURITY.md](SECURITY.md) for the list of sensitive subsystems — changes
  there require review from the relevant code owners in
  [.github/CODEOWNERS](.github/CODEOWNERS)).

## Pull request workflow

1. **Fork** the repository (or, for maintainers, branch directly).
2. **Create a branch** off `main` with a short, descriptive, conventional-ish
   name, for example:
   - `feat/cross-file-resolution-rust`
   - `fix/receipt-merkle-chain-offset`
   - `docs/contributing-refresh`
   - `chore/bump-tree-sitter`
3. **Make focused commits.** Use clear, imperative commit messages
   (`Add ...`, `Fix ...`, `Refactor ...`). Keep unrelated changes in separate
   commits or PRs.
4. **Run the CI commands above** until they pass locally.
5. **Open a pull request** against `main`. Fill out the PR template, link any
   related issue, and describe behavior changes and security-sensitive paths.
6. **Respond to review.** Keep the branch up to date with `main` and address
   review comments with follow-up commits.

Do not include secrets, customer code, generated credentials, or proprietary
third-party artifacts in any commit or PR.

## Developer Certificate of Origin (sign-off)

All commits must be signed off under the
[Developer Certificate of Origin (DCO)](https://developercertificate.org/). By
signing off, you certify that you wrote the contribution or otherwise have the
right to submit it under the project license.

Add a sign-off line to each commit:

```bash
git commit -s -m "Fix receipt Merkle chain offset"
```

This appends a trailer of the form:

```
Signed-off-by: Your Name <you@example.com>
```

Commits without a `Signed-off-by` trailer may be asked to be amended before
merge.

## Getting help and reporting problems

- Usage and evaluation questions, bug reports, and feature requests: see
  [.github/SUPPORT.md](.github/SUPPORT.md) and the issue templates under
  `.github/ISSUE_TEMPLATE/`.
- Conduct concerns: see [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md).
- Security vulnerabilities: see [SECURITY.md](SECURITY.md) — never via a public
  issue.
