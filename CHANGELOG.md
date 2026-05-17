# Changelog

All notable changes to OMNIX are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-05-16

### Changed
- **Namespace restructure (slice 21.7 phase B):** all OMNIX source modules now live under the `omnix.*` Python namespace package (`src/omnix/`). Top-level packages `src/agents/`, `src/parser/`, `src/graph/`, `src/axiom/`, `src/fabric/`, `src/providers/`, `src/find_bugs/`, `src/verify/`, `src/scan/`, `src/studio/`, `src/mcp/` were moved under `src/omnix/<name>/`. Public CLI surface (`omnix analyze`, `omnix grammar`, `omnix find-bugs`, `omnix verify`) is unchanged. Import paths inside the codebase updated throughout (302 file renames + 99 internal import-path updates). `omnix.py` shim at repo root handles both script invocation and `import omnix` usage so external integrators see a stable entry point.
- **pyproject.toml version reconciled** from stale `0.1.0` to the actual `0.6.0`. `omnix_version.py` was the de-facto version source; pyproject had drifted since first commit. Both now agree.

### Fixed
- **Turboscan filesystem-hygiene env propagation through forkserver (slice 21.7 phase C):** on Python 3.14+ the turboscan worker pool uses `forkserver`, which snapshots `os.environ` at first use. Subsequent updates to the parent's env never reach worker children, so per-codebase `OMNIX_FS_HYGIENE_*` config was being stripped at the worker boundary. Fix threads the hygiene env explicitly through `run_args` via a new `subprocess_env_overrides` key; `_run_verify_limited` applies it to the env dict handed to subprocess. Verified by `tests/scan/test_hygiene_integration_with_find_bugs.py` (2 passed, was 2 failed before).
- **`omnix grammar list` off-by-one (slice 21.7 phase C):** `suf = n[13:]` stripped one character beyond the 12-char `tree_sitter_` prefix, printing `tree_sitter_ava/ava` instead of `tree_sitter_java/java` for every language. Replaced with `n[len("tree_sitter_"):]`.
- **Forkserver env cleanup completeness — toggle pattern (slice 21.7 phase C.1, codex adversarial follow-up):**
  - `_run_verify_limited` previously only SET hygiene env keys via `subprocess_env_overrides` and never CLEARED them. A hygiene-disabled scan running after a hygiene-enabled scan in the same parent process could inherit stale `OMNIX_FS_HYGIENE_REPO_ROOT`/`_STRICT`/etc., causing hygiene findings to fire against the wrong repo. Fix: when `OMNIX_FS_HYGIENE_ENABLED` is absent from overrides, pop all `_HYGIENE_ENV_KEYS` from env before applying overrides.
  - `_child_verify` (Hypothesis-import fallback path) dropped `subprocess_env_overrides` entirely, reintroducing the staleness bug when that fallback fired. Fix: mirror `_run_verify_limited`'s pop-then-apply logic on `os.environ` inside the child.
  - New regression suite at `tests/scan/test_hygiene_env_toggle.py` (3 tests) exercises the toggle pattern and the fallback path.

### Internal
- Test suite: 478 → 481 passing (+3 from phase C.1 regression tests). 5 skipped (intentional env-gated perf tests + one parser_bridge placeholder).
- Frontend test suite: 248 passing.
- Codex adversarial review run on phase C surfaced two findings (HIGH + MEDIUM); both fixed in phase C.1 within the same PR.
