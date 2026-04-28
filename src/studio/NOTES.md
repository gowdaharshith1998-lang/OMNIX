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

