# test_workspace_dedupe.py — BLOCKED (out of scope)

**Original location:** `tests/studio/test_workspace_dedupe.py`
**Blocked since:** 2026-05-16 (pre-M1)

## Why this test cannot be xfailed (and is moved instead)

Running this test in isolation SEGFAULTS the pytest process (Python 3.14.4, sqlite3
extension). The fatal Python error during test teardown originates in
`omnix/graph/store.py:close()` racing with an asyncio executor thread invoking
`omnix.parser.ingest_dispatch._maybe_invalidate_ingest_cache` from the studio
server lifespan. The crash kills the entire pytest session — not just the test —
making it impossible to apply an `xfail` marker (pytest never gets to record the
xfail because the process is already gone).

When run as part of the full suite, this crash takes down every test that would
have run after `test_workspace_dedupe`. It surfaced during the pre-M1
test-classification pass.

## What needs to land before this can be restored

- `omnix.graph.store.GraphStore.close()` must drain in-flight async readers before
  closing the sqlite connection (currently it closes immediately, leaving the
  ingest cache thread holding a freed pointer).
- The `_lock` RLock specced by the xfailed
  `tests/graph/test_store_locking.py::test_store_has_rlock` is a prerequisite —
  the close path needs to acquire the lock to serialize against in-flight writes.

## Tracking

Tracked as a known pre-M1 limitation (`workspace-dedupe-segfault`), sharing a root
cause with the graph-store-locking work.

## How to restore

After the GraphStore close path is hardened (depends on the RLock landing):
```bash
git mv tests/_blocked/studio/test_workspace_dedupe.py tests/studio/test_workspace_dedupe.py
rm tests/_blocked/studio/test_workspace_dedupe.WHY.md
# Clear the workspace-dedupe-segfault tracking entry.
pytest tests/studio/test_workspace_dedupe.py -v
# Confirm no segfault during teardown.
```
