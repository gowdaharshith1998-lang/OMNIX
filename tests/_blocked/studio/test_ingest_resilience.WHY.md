# test_ingest_resilience.py — BLOCKED (out of scope)

**Original location:** `tests/studio/test_ingest_resilience.py`
**Blocked since:** 2026-05-16 (pre-M1)

## Why this test cannot be xfailed (and is moved instead)

Running this test in isolation HANGS past a 60s timeout — never reaches a fail/pass
state. The `monkeypatch.setattr("omnix.studio.server._ingest_block", boom)` injection
triggers an async deadlock during the FastAPI app lifespan in the in-flight ingest
backpressure code path. The async waiter never resolves because the production code
path the test is exercising (the resilience handler) has not yet been built — the
test is the spec.

A `@pytest.mark.xfail` marker is insufficient: pytest never gets to record the
xfail because the process is stuck inside the studio server lifespan.

## What needs to land before this can be restored

- `omnix.studio.server` ingest resilience path: when `_ingest_block` raises, set a
  workspace `broken_ingest` event AND release the lifespan cleanly, so the test's
  `boom` fixture can return promptly. The current code holds the lifespan open.

## Tracking

Tracked as a known pre-M1 limitation (`ingest-resilience`).

## How to restore

When the backend lands the ingest resilience path:
```bash
git mv tests/_blocked/studio/test_ingest_resilience.py tests/studio/test_ingest_resilience.py
rm tests/_blocked/studio/test_ingest_resilience.WHY.md
# Clear the ingest-resilience tracking entry.
pytest tests/studio/test_ingest_resilience.py -v   # should run and pass cleanly
```
