# test_ingest_resilience.py — BLOCKED-OUT-OF-SCOPE

**Original location:** `tests/studio/test_ingest_resilience.py`
**Blocked since:** slice 21.8 (M0.5 dispatch, 2026-05-16)
**Stash origin:** `wip-slice-15.3.7-and-misc-post-PR`

## Why this test cannot be xfailed (and is moved instead)

Running this test in isolation HANGS past a 60s timeout — never reaches a fail/pass
state. The `monkeypatch.setattr("omnix.studio.server._ingest_block", boom)` injection
appears to trigger an async deadlock during the FastAPI app lifespan in slice 15.3.7's
in-flight ingest backpressure code path. The async waiter never resolves because the
production code path the test is exercising (slice 15.3.7's resilience handler) has
not yet been built — the test is the spec.

A `@pytest.mark.xfail` marker is insufficient: pytest never gets to record the
xfail because the process is stuck inside the studio server lifespan.

## What needs to land before this can be restored

- `omnix.studio.server` ingest resilience path: when `_ingest_block` raises, set a
  workspace `broken_ingest` event AND release the lifespan cleanly, so the test's
  `boom` fixture can return promptly. The current code holds the lifespan open.

## TODOS.md tracking

P1: `slice-15.3.7-ingest-resilience` — see `/TODOS.md`.

## How to restore

When slice 15.3.7 backend lands the ingest resilience path:
```bash
git mv tests/_blocked/studio/test_ingest_resilience.py tests/studio/test_ingest_resilience.py
rm tests/_blocked/studio/test_ingest_resilience.WHY.md
# Remove the TODOS.md P1 entry.
pytest tests/studio/test_ingest_resilience.py -v   # should run and pass cleanly
```
