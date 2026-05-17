# Changelog

All notable changes to OMNIX are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.1] - 2026-05-17

### Changed
- **Slice 15.3.7 LLM tool-dispatch source landed in `omnix.*` namespace (slice 21.8 / M0.5):** the WIP from stash `wip-slice-15.3.7-and-misc-post-PR` was applied onto a new branch off main, file-moved into the namespaced tree (`src/fabric/dispatch_tools.py` → `src/omnix/fabric/dispatch_tools.py`; `src/providers/tools/` → `src/omnix/providers/tools/`; 18 React/TS files under `src/studio/frontend/src/` merged into the existing `src/omnix/studio/frontend/src/` tree), and every `from src.X` / bare `from fabric|providers` import (plus the inline `monkeypatch.setattr("src.X...")` / `@mock.patch("fabric...")` string paths) retargeted to `from omnix.X`. Collision survey at `/tmp/slice-15.3.7-collision-manifest.md` confirmed 0 IDENTICAL, 0 COLLISION, 30 NEW — clean merge with no manual escalation.
- **`omnix.axiom` Python module renamed to `omnix.receipts` (M0 leftover folded into M0.5):** the module that emits and verifies signed receipts is now named for what it does, not for the marketing surface. 17 tracked files renamed via `git mv` (history preserved); 38 source files updated to import from `omnix.receipts` (every `omnix.axiom` dot-path reference + the two hardcoded internal-tree filesystem paths in `walker.py`'s pathological-skip list and `test_loader.py`'s ENCODING constant). **The user-facing CLI verb tree is unchanged** — `omnix axiom keygen`, `omnix axiom verify-scan`, and `omnix axiom export-vault` all still work; only the internal Python module path moved. The audit-export.zip shipped to early users continues to reference the `omnix axiom` verbs verbatim. Sibling-repo `apps/backend/src/omnix/axiom` references in `src/web/graph_data_axiom_v2.json` and the frontend AXIOM-V2 fixtures were deliberately NOT swept (they describe AXIOM-V2 paths, not our OMNIX module).

### Added
- **8 slice 15.3.7 Python test files classified per a verdict manifest** (`/tmp/slice-15.3.7-test-verdicts.md`):
  - 1 file PASSING (`tests/fabric/test_dispatch_tools_integration.py`, 3/3 green).
  - 3 files MIXED with per-test `@pytest.mark.xfail(strict=True, reason=...)` markers naming the exact missing slice 15.3.7 symbol: `tests/fabric/test_dispatcher_provider_override.py` (1 pass + 4 xfail on `dispatcher.dispatch(provider_override=…)`), `tests/fabric/test_real_tool_use.py` (3 pass + 2 xfail on `openai_compatible.call(tools=…)` and `dispatcher._tool_use_message_list`), `tests/graph/test_store_locking.py` (1 pass + 4 xfail on `GraphStore._lock` / `.locked_connection()` / serialized writes; the concurrent-writes test uses `strict=False` because it passes in isolation but fails under full-suite load).
  - 2 files module-level `pytestmark = pytest.mark.xfail(strict=True)` because every test in the file depends on the same unbuilt slice 15.3.7 surface: `tests/fabric/test_provider_error_detail.py` (2 tests, `body_text`/`body_json` response fields not yet emitted) and `tests/studio/test_action_dispatch_route.py` (10 tests, `/action/dispatch` route + `omnix.studio.server.get_provider_client` symbol not yet built).
  - 2 files BLOCKED-OUT-OF-SCOPE — moved to `tests/_blocked/studio/` with sibling `.WHY.md` files, because they cannot be xfailed: `test_ingest_resilience.py` hangs past 60s on an async deadlock in the studio server lifespan when `_ingest_block` raises, and `test_workspace_dedupe.py` segfaults Python 3.14 / sqlite3 during teardown (GraphStore.close races with the ingest cache thread). Both have P1 entries in `TODOS.md`.
- **`TODOS.md` (new):** seven P1 entries naming the exact symbol each xfailed/blocked test needs in order to unblock (e.g. `slice-15.3.7-provider-override-kwarg`, `slice-15.3.7-graph-store-locking`, `slice-15.3.7-action-dispatch-backend`).
- **`tests/_blocked/` directory convention:** opt-out collection via `pyproject.toml` `[tool.pytest.ini_options]` `norecursedirs = ["_blocked", ...]` (pytest defaults preserved explicitly because `norecursedirs` replaces rather than extends). Each blocked test has a sibling `<name>.WHY.md` documenting root cause + restore checklist.

### Internal
- Test suite: 481 → 488 backend passing (+7 from PASSING-bucket stashed tests landing) + 22 xfailed (the slice 15.3.7 spec markers) + 5 skipped (unchanged). 1 pre-existing positioning test (`test_readme_company_brain_opening`) still fails on main HEAD due to README rewrite drift — NOT caused by this PR; deferred to its own one-line dispatch. No new failures introduced by this PR.
- Six commits on the slice-21-8-tool-dispatch-namespace branch: backend moves + frontend moves + import retargets + test classification + cleanup + receipts rename + this version bump.
- The `wip-slice-15.3.7-and-misc-post-PR` stash is intentionally NOT dropped — kept as recovery insurance until this PR lands.

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
