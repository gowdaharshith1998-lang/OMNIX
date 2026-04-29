# Studio Notes

## Phase 14c — accumulated debt (T2 v2 slice 3 close-out, Day 5)

Items below were observed during slice 3 backend diagnosis but are
out of slice 3 scope. Address during T3 or polish window.

- [debt-13] ~~Backend live-emission gap~~ **RESOLVED (T3, 2026-04-28).**
  Diagnosis (Case B): `compute_file_delta` correctly returned an empty
  dict when file bytes changed but graph nodes/edges matched the prior
  snapshot (e.g. editing only a literal inside a function leaves the same
  NodeRow signatures). The bridge still ran ingest and updated `file_hashes`;
  subsequent watcher noise correctly hit `hash_skip`. The user-visible gap
  was no WS verb for “disk content changed, AST snapshot unchanged.” Fix:
  `parser_bridge._process_one` emits a synthetic `node_modified` for one
  representative node (prefer function/method/class) when a prior
  `file_hashes` row exists, stored sha differs from disk sha, the delta is
  empty, and the file still has nodes—unblocking StudioGraph rim flash and
  parity with slices 3–6d expectations. Instrumentation: structured INFO logs
  (`hash_skip`, `delta_computed`, `broadcast`, `synthetic_node_modified`,
  `ingest_skip_or_error`, `pump_exception`); opt-in stderr handler for
  `omnix.studio.parser_bridge` when `OMNIX_STUDIO_DEBUG=1`. Tests:
  `tests/studio/test_t3_live_emission.py` (edit → synthetic modified, add
  function → node_added, delete → node_removed).

- [debt-14] _stats_ticker (`server.py` 466–487) emits stats every ~0.5s to
  all subscribed sockets — high-frequency flood that could swamp the delta
  channel under load. Consider: backpressure, reduce cadence, or batch with
  delta emits. Not blocking; defer.

- [debt-15] Subscribe path (`server.py` 512–517) returns 403 on stale
  `workspace_id` without rich error info — hard to debug in the browser
  console. Add structured error payload. Defer.

- [debt-32] `compute_file_delta` (`delta.py` 45–47) docstring mentions
  `modified_edges` but the return dict (91–98) omits it. Doc/code drift.
  Either implement or remove from docstring. Defer until edge_modified
  design lands (slice 7).

- [debt-16] ".omnix" string literal hardcoded in multiple places
  (paths.py:25, watcher.py:21). Promote to shared OMNIX_DIR_NAME
  constant in src/omnix/state.py or src/studio/constants.py.

- [debt-17] Live mode bridge (graphNode.ts wsNodeToViewerShape) does
  not preserve type='dark_matter' or type='entangled_pair' from the
  WS payload. Falls through to default branch (gray). Result: live
  mode shows 0 dark matter and 0 entangled pairs even though analyze
  detects them. T1 mode renders them correctly. Must port type
  handling from T1's bundled JSON path to live bridge.

- [debt-18] Multiple analyze viewer features missing from live Studio:
  dark matter highlighting toggle effect, entangled pairs animation,
  cluster colors (Louvain), timeline scrubbing data, dark force/dark
  energy visualizations. T1 mode (?t1=1) has these; live mode bridge
  drops them. See debt-17 for the bridge layer; deeper than just
  type preservation. Inventory to be filed in slice 6 / T3.


## Phase 14c — feature parity audit (Day 5 evening)

Comparison live mode (port 7778) vs analyze viewer (port 7777).
Diagnosis traced through wsNodeToViewerShape, node_row_to_dict,
server.py routes inventory.

### Missing in live mode

- [debt-19] wsNodeToViewerShape (graphNode.ts) does not have a
  branch for type='dark_matter'. Falls through to default branch:
  color #94a3b8 gray, val 1. Should be: color #8b5cf6 violet,
  val 2, with metadata flag for dark matter renderer to pick up.
  Backend correctly emits type='dark_matter' via node_row_to_dict.
  Frontend bridge is the gap. Fix: ~30 LOC, ~0.5d. Severity: visible
  in StatsPanel as "Dark Matter: 0" because no nodes pass dark
  matter detection on frontend.

- [debt-20] Same as debt-19 for entangled pairs. Backend stats track
  entangled count via workspace.py:59 SQL. Bridge has no branch for
  type='entangled_pair' (or whatever the type string actually is —
  needs verification by checking sample WS payload). Fix together
  with debt-19 in single bridge enhancement.

- [debt-21] /api/timeline is currently a quiet compatibility endpoint
  returning an empty snapshot list. Frontend at viewerEngine.ts line ~4959
  has applyTimelineSnapshot and applyTimelineToPixiContainers code, but
  live mode has no real git-history source yet. Defer real timeline data
  to Phase 15. Severity: cosmetic.

- [debt-22] /api/ai/status is currently a quiet compatibility endpoint
  that reports unavailable. /api/ai/diagnose, /api/ai/security,
  /api/ai/architecture, /api/ai/ask endpoints all missing from
  server.py. These get built natively as part of Day 15 Agent tab work.
  Do NOT split into separate slice. Severity: AI agent panel currently
  non-functional, but planned.

- [debt-23] After debt-19/20 fix, verify viewerEngine dark matter
  toggle (line ~5620) actually picks up the type field from bridged
  nodes. Code path: btn-dark-matter click → toggles ql variable →
  QF dark matter render fn iterates nodes by type. Likely works
  once bridge passes the type, but needs visual verification.
  Severity: blocker for debt-19 actually being visible.

- [debt-24] Backend node_row_to_dict does not emit cluster_id field.
  T1 bundled JSON has Louvain cluster ids per node which drive the
  galaxy layout (cluster-colored, cluster-positioned). Live mode WS
  bootstrap sends flat node dicts; galaxy renders flat-radial, not
  clustered. Fix: extend node_row_to_dict to query cluster from DB
  (add cluster table if not present) and include in payload. Cost:
  ~1.5d split between backend SQL/algo and frontend layout adoption.
  Severity: live mode galaxy looks visibly less informative than
  analyze viewer galaxy. Significant for Day 24 demo aesthetic.

- [debt-25] After node_removed splice, drawSubviewPhysarumEdges
  (viewerEngine.ts:4524-4617 — range shifts if viewerEngine edits)
  does not filter edges whose endpoints are no longer in pc._nodes.
  The endpoint node object still has .x/.y properties post-splice, so
  edges draw into empty space (orphan stub edges). Slice 4 accepts
  this as deferred — fix is to either (a) add membership check in
  drawSubviewPhysarumEdges loop, or (b) prune pc._edges when a node
  is spliced. Option (b) is cleaner long-term. Cost: ~0.5d.
  Severity: visible visual artifact after every node_removed; minor
  at low removal frequency, ugly at high frequency.

- [debt-26] `viewerEngine` planet cell construction is duplicated between
  `createPlanetView` (bootstrap) and `_bornNode` (T2 v2 slice 5 live add).
  Extract a shared `buildPlanetNodeRef(fileData, fp, sym, j, …)` in a
  dedicated refactor commit to avoid drift.

- [debt-27] Closed by slice 14.5: `scripts/build_studio_viewer_engine.py`
  and `src/web/index.html` were deleted with the legacy viewer. `viewerEngine.ts`
  is now explicitly hand-maintained until debt-16 removes the remaining
  superseded viewer helpers.

- [debt-30] Optional follow-up: if live CALLS edges feel visually abrupt (no gsap
  on edge geometry), add a short gsap alpha/stroke reveal after `_bornEdge`;
  slice 6a relies on physarum painter-only fade-in.

- [debt-31] Live CALLS dedup uses **unordered** synth pair (matches static
  `buildPlanetEdgeList`). Directional A→B vs B→A as distinct edges is **not**
  implemented; file a feature slice if product wants asymmetric CALLS.

### Inventory of T1 vs live divergence

T1 bundled sample mode:
  - Node types: file, directory, function, method, class, dark_matter
  - Link types: CALLS, IMPORTS, INHERITS, DECORATES, DEFINES, ENTANGLED, DARK_FORCE
  - Per-node fields: cluster_id, val, color
  - Timeline data: no active live source; /api/timeline is an empty compatibility stub

Live mode (Studio at :7778) currently passes through bridge:
  - Node types correctly preserved BUT only file/dir/folder/function/
    method/class get type-aware rendering. dark_matter falls through.
  - Link types: untested for ENTANGLED/DARK_FORCE preservation
  - cluster_id: MISSING — debt-24
  - Timeline: empty compatibility endpoint — debt-21

## Slice 6c — reconnect policy: Option B (preserve + rebootstrap-in-place)

Decision rationale: The existing pipeline already implements Option B implicitly.
`StudioGraph` stays mounted across socket drops; `bootstrap_start` cleanly resets
`_bootstrapBuffer` (`StudioGraph.ts` 235–246); the server runs `_run_bootstrap` on
every successful subscribe (`server.py` 519–521); `_wsIdToSynthId` rebuilds in
`_renderBufferedSnapshot` (`StudioGraph.ts` 187–200).

Slice 6c formalizes the policy with regression tests proving mid-session bootstrap
cycles plus a small UX indicator showing reconnect status. **Not** a behavior change.

Future devs: Do **not** introduce A-shaped destroy-and-rebuild on socket close.
Viewer state (`camera`, `viewLevel`, `selectedFile`) intentionally survives reconnect;
rebuilding `StudioGraph` resets all of it.

Option C (delta-resume with server-side delta log + sequence numbers) is the
eventual right answer for bandwidth efficiency but punted to post-Day 24.

Refs: slice 6c RECON manifest (Studio tab); slice 6 RECON Concern C.

### Generator check (debt-27)

Closed by slice 14.5; `viewerEngine.ts` is hand-maintained in React Studio.

## Slice 6d — bootstrap UX (Option A)

First-load ambiguity (“still loading” vs “broken”) before the first `bootstrap_complete`
is addressed with a small **BootstrapIndicator** overlay (`BootstrapIndicator.tsx`):
parse `bootstrap_complete` in the existing `Workspace` WebSocket message callback (before
`graphRef.ingestMessage`), set `hasBootstrappedRef`, fade out over 200ms, then unmount.

Reconnect suppression uses **`!isReconnecting`** — not `!hasConnectedBeforeRef.current`,
because the latter flips true on first `open` **before** `bootstrap_complete` and would
suppress the overlay during the real first load. `?t1=1` / T1 mode gates the overlay off
(no live bootstrap). Layout matches slice 6c: `fixed right-3 top-16 z-[35]` (below
StatsPanel at `top-5`).

## T3 closure (2026-04-28)

Debt-13 backend live emission: synthetic `node_modified` when disk sha differs from
`file_hashes` but `compute_file_delta` is empty; structured ParserBridge logging (opt-in
`OMNIX_STUDIO_DEBUG=1`). New integration tests `tests/studio/test_t3_live_emission.py`.
Test counts: pytest 305 (+3 vs pre-T3), vitest 38 unchanged. Fix commit on `main`: `8f68098`.

