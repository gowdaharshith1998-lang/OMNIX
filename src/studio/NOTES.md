# Studio Notes

## Phase 14c — accumulated debt (T2 v2 slice 3 close-out, Day 5)

Items below were observed during slice 3 backend diagnosis but are
out of slice 3 scope. Address during T3 or polish window.

- [debt-13] Backend live-emission gap: real file edits in workspace
  do not produce node_added or node_modified WS broadcasts to
  subscribed tabs. Watcher fires (verified — DB mtime updates), but
  bridge → broadcast pipeline silently drops the event.
  _STD_IGNORE_DIR_PARTS and _ok_path are NOT the cause (.omnix
  already filtered). Likely candidates: (a) ParserBridge debounce
  never flushes due to repeated event cancellation, (b)
  compute_file_delta returns empty dict for the edit type, (c)
  evolution.finalize writes create their own loop, (d) workspace ID
  mismatch between watcher event broadcast target and tab's
  subscribe registration. To diagnose: full trace of
  ParserBridge._pump body + _ingest_block + evolution write paths.
  Block: prevents visual verification of slices 3, 4, 5 (all delta
  types). Recommended T3 work item.

- [debt-14] _stats_ticker fires unconditionally every 0.5s while WS
  open (server.py:_stats_ticker). At idle this produces ~2 stats
  msgs/sec to every connected tab. Should be (a) >=5s interval AND
  (b) gated on stats_dict() change since last tick. Cosmetic but
  floods DevTools console at debug verbosity.

- [debt-15] WebSocket subscribe handshake returns HTTP 403 when tab
  holds a stale workspace_id from a previous server session. Studio
  frontend should detect 403 on reconnect, drop cached workspace_id,
  redirect to picker. Currently silently retries forever.

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

- [debt-21] /api/timeline endpoint does not exist in server.py.
  Frontend at viewerEngine.ts line ~4959 has applyTimelineSnapshot
  and applyTimelineToPixiContainers code. T1 mode bundles
  timeline_data.json; live mode has no source. Frontend logs 404
  every page load. Defer to Phase 15: niche feature, backend would
  need to expose git history snapshots. Severity: cosmetic.

- [debt-22] /api/ai/status, /api/ai/diagnose, /api/ai/security,
  /api/ai/architecture, /api/ai/ask endpoints all missing from
  server.py. Frontend X-RAY panel renders "AI Agent unavailable —
  set OMNIX_AI_KEY or install Ollama" because /api/ai/status 404s.
  These get built natively as part of Day 15 Agent tab work. Do
  NOT split into separate slice. Severity: AI agent panel currently
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

- [debt-27] `scripts/build_studio_viewer_engine.py` generates `viewerEngine.ts`
  from `src/web/index.html` plus small string patches. Studio-only hooks
  (`_flashNodeRim`, `_fadeAndRemoveNode`, `_bornNode`, `_bornEdge`, etc.) are **not** in the
  generator — they live only in `viewerEngine.ts`. Running `main()` on the
  script overwrites those slices unless the pipeline is extended to splice in
  Studio hooks from a patch file or forked template. Decide whether to wire
  generator + Studio overlay or stop regenerating until reconciled.
  Slice 6a verification (2026): grep of `build_studio_viewer_engine.py` shows no
  `_bornEdge` / slice 6 references — unchanged risk profile vs slice 5.

- [debt-30] Optional follow-up: if live CALLS edges feel visually abrupt (no gsap
  on edge geometry), add a short gsap alpha/stroke reveal after `_bornEdge`;
  slice 6a relies on physarum painter-only fade-in.

- [debt-31] Live CALLS dedup uses **unordered** synth pair (matches static
  `buildPlanetEdgeList`). Directional A→B vs B→A as distinct edges is **not**
  implemented; file a feature slice if product wants asymmetric CALLS.

### Inventory of T1 vs live divergence

T1 bundled (analyze viewer at :7777):
  - Node types: file, directory, function, method, class, dark_matter
  - Link types: CALLS, IMPORTS, INHERITS, DECORATES, DEFINES, ENTANGLED, DARK_FORCE
  - Per-node fields: cluster_id, val, color
  - Timeline data: separate JSON

Live mode (Studio at :7778) currently passes through bridge:
  - Node types correctly preserved BUT only file/dir/folder/function/
    method/class get type-aware rendering. dark_matter falls through.
  - Link types: untested for ENTANGLED/DARK_FORCE preservation
  - cluster_id: MISSING — debt-24
  - Timeline: 404 — debt-21

