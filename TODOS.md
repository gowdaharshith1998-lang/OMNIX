# OMNIX — TODOS

Cross-slice P1 follow-ups. Entries are added/removed by named slices.

---

## P1 — slice 15.3.7 follow-ups (logged by slice 21.8 / M0.5)

Slice 21.8 (M0.5) landed the slice 15.3.7 LLM tool-dispatch source into the
`omnix.*` namespace but classified eight stashed test files into `PASSING /
XFAIL-WITH-REASON / BLOCKED-OUT-OF-SCOPE` buckets. The xfail-strict and blocked
tests are the spec for slice 15.3.7's unbuilt features. The list below is the
backlog those tests track:

### slice-15.3.7-provider-error-detail
Make `omnix.fabric.providers.openai_compatible.call()` return a response dict that
includes `body_text` and `body_json` fields on HTTP errors (currently the dict
lacks those keys). When this lands, `tests/fabric/test_provider_error_detail.py`'s
two xfail-strict tests will start XPASSING — pytest will fail the run until the
xfail decorator is removed.

### slice-15.3.7-tools-param-on-openai-compatible
Add a `tools` keyword parameter to `omnix.fabric.providers.openai_compatible.call()`
so providers can declare the OpenAI tool-use schema. Specced by
`tests/fabric/test_real_tool_use.py::test_openai_compatible_accepts_tools_parameter`.

### slice-15.3.7-dispatcher-tool-use-message-list
Add a `_tool_use_message_list` helper to `omnix.fabric.dispatcher` that builds the
multi-turn tool-use message envelope. Specced by
`tests/fabric/test_real_tool_use.py::test_dispatcher_has_tool_definitions_option_path`.

### slice-15.3.7-provider-override-kwarg
Add a `provider_override` keyword parameter to `omnix.fabric.dispatcher.dispatch()`
that pins the call to a single provider (skipping the failover chain). Specced by
the four xfail-strict tests in `tests/fabric/test_dispatcher_provider_override.py`
(constrains_candidate_list, missing_key_returns_without_failover,
transient_retries_same_provider_only, non_transient_error_returns_immediately).

### slice-15.3.7-graph-store-locking
Add a `_lock` `threading.RLock` field + `.locked_connection()` context manager to
`omnix.graph.store.GraphStore` so concurrent writes are serialized. Specced by
`tests/graph/test_store_locking.py`'s three xfail-strict tests
(test_locked_connection_select, test_rlock_nested_locked_connection,
test_store_has_rlock). Prerequisite for unblocking the
`slice-15.3.7-workspace-dedupe-segfault` item below.

### slice-15.3.7-action-dispatch-backend
Build the `/action/dispatch` FastAPI route + `get_provider_client` symbol in
`omnix.studio.server`. Specced by all 10 tests in
`tests/studio/test_action_dispatch_route.py` (module-level xfail-strict). The
React frontend in `omnix.studio.frontend.components.actions.*` is already in
place (landed by slice 21.8) — it currently calls into a route that returns 404.

### slice-15.3.7-ingest-resilience
Harden the `omnix.studio.server._ingest_block` path so that when ingest raises,
the workspace's `broken_ingest` event is set and the FastAPI app lifespan
releases cleanly (without the async deadlock that currently makes the test hang).
Specced by `tests/_blocked/studio/test_ingest_resilience.py` (BLOCKED — hangs
past 60s timeout, can't be xfailed). See its `.WHY.md` sibling.

### slice-15.3.7-workspace-dedupe-segfault
Make `omnix.graph.store.GraphStore.close()` drain in-flight async readers before
closing the sqlite connection. Currently the close path races with the ingest
cache thread, segfaulting Python 3.14 / sqlite3 extension during teardown.
Specced by `tests/_blocked/studio/test_workspace_dedupe.py` (BLOCKED — segfaults
pytest, can't be xfailed). Depends on `slice-15.3.7-graph-store-locking`.

---

## P1 — housekeeping (logged by post-M0.5 stand-down)

### slice-21-10-hex-fps-perf-flake
Investigate why `src/omnix/studio/frontend/src/components/Graph/__tests__/hex-fps-perf.test.tsx::test_fps_floor_at_full_load` passes in isolation (`npm test -- --run hex-fps-perf.test.tsx` → 2/2 green) but fails under full-suite parallel load (`npm test -- --run` → 1 failed). Suspected root cause: shared module state across vitest workers (the FPS ticker/galaxyStressHarness probably leaks singleton state between parallel worker contexts), or worker-isolation config drift. Not blocking — the failure is non-deterministic and the test isn't part of any prod path. Ranks first in the next housekeeping window before CI gets wired, since a CI-wired flake floods the PR-status signal.

Restore criteria: deterministic green/red on `npm test -- --run` across 10 consecutive runs.

---

When a slice lands one of these features and the xfailed/blocked tests start
passing, remove the corresponding entry from this file in the same PR.
