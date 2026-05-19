# OMNIX AUDIT REPORT
Date: 2026-04-14

> Archived historical audit. Slice 14.5 retired the legacy static viewer
> described here (`src/web/index.html`, `/api/graph`, generated graph/timeline
> JSON targets, and `tests/sidebar/**`). Current `omnix analyze` serves React
> Studio from `src/studio/frontend/dist/` against the Studio SQLite/WebSocket
> pipeline.

## Summary
- Total Python source files (excluding `__pycache__`): **19** (~3,737 lines via `wc`)
- Total HTML files: **1** (`src/web/index.html`, 4,915 lines)
- Approximate tracked source lines (Python + main HTML): **~8,650** (plus `README.md`, `requirements.txt`, JSON artifacts)
- Import checks (as specified in Step 2): **10 / 12 pass** (`parse_python` and `parse_typescript` are not exported; real names are `parse_python_files` and `parse_typescript_files`)
- `index.html` feature checklist (Step 6): **30 / 30 EXISTS** (working implementation present; see Feature Audit for notes)
- Automated tests: **3 passed** (`pytest tests/ -q`)

## File Inventory

| File path | Line count | Last modified (local) | Purpose |
|-----------|------------|------------------------|---------|
| `./.gitignore` | 7 | 2026-04-14 02:15:07 | Git ignore rules for the repo. |
| `./omnix.db` | *(binary)* | 2026-04-14 23:20 | SQLite graph database produced by analyze. |
| `./omnix.py` | 266 | 2026-04-14 12:39:03 | CLI entry: `analyze` command, graph export, embedded HTTP server for the web UI. |
| `./__pycache__/omnix.cpython-314.pyc` | — | 2026-04-14 12:40:39 | Bytecode cache for `omnix.py`. |
| `./README.md` | 36 | 2026-04-14 00:08:24 | Project overview and usage. |
| `./requirements.txt` | 3 | 2026-04-14 00:08:22 | Python dependencies. |
| `./src/agents/__init__.py` | 1 | 2026-04-14 12:37:17 | Agents package marker. |
| `./src/agents/llm_router.py` | 232 | 2026-04-14 12:37:31 | Routes LLM calls to OpenAI-compatible API or Ollama. |
| `./src/agents/memory.py` | 129 | 2026-04-14 12:37:43 | SQLite-backed feedback memory for agent diagnoses. |
| `./src/agents/orchestrator.py` | 382 | 2026-04-14 14:22:58 | High-level AI workflows (diagnose, security, architecture, ask). |
| `./src/agents/tools.py` | 273 | 2026-04-14 12:41:01 | DB/file/git tools used by orchestrator and MCP. |
| `./src/agents/__pycache__/*.pyc` | — | 2026-04-14 | Bytecode caches for agents. |
| `./src/graph/__init__.py` | 0 | 2026-04-13 23:54:52 | Graph package marker. |
| `./src/graph/exporter.py` | 78 | 2026-04-14 02:01:59 | Exports `GraphStore` to JSON for the web viewer. |
| `./src/graph/store.py` | 191 | 2026-04-14 02:01:12 | SQLite graph persistence (nodes, edges, reset, counts). |
| `./src/graph/__pycache__/*.pyc` | — | 2026-04-14 | Bytecode caches for graph. |
| `./src/__init__.py` | 0 | 2026-04-13 23:54:52 | Src package marker. |
| `./src/mcp/__init__.py` | 0 | 2026-04-14 12:38:25 | MCP package marker. |
| `./src/mcp/server.py` | 237 | 2026-04-14 23:18:30 | Stdio MCP server: JSON-RPC `initialize`, `tools/list`, `tools/call`. |
| `./src/mcp/__pycache__/server.cpython-314.pyc` | — | 2026-04-14 | Bytecode cache for MCP server. |
| `./src/parser/dark_matter_parser.py` | 206 | 2026-04-14 02:00:36 | Detects “dark matter” dependency nodes (e.g. env/config). |
| `./src/parser/entanglement_parser.py` | 259 | 2026-04-14 02:01:38 | Detects cross-module entanglement edges. |
| `./src/parser/git_parser.py` | 156 | 2026-04-14 02:15:14 | Builds git timeline snapshots for the scrubber UI. |
| `./src/parser/__init__.py` | 26 | 2026-04-13 23:59:54 | Parser package exports. |
| `./src/parser/python_parser.py` | 619 | 2026-04-14 00:02:49 | Tree-sitter Python parsing into the graph. |
| `./src/parser/typescript_parser.py` | 592 | 2026-04-14 00:06:16 | Tree-sitter TS/TSX parsing into the graph. |
| `./src/parser/__pycache__/*.pyc` | — | 2026-04-14 | Bytecode caches for parsers. |
| `./src/__pycache__/__init__.cpython-314.pyc` | — | 2026-04-14 | Bytecode cache. |
| `./src/web/graph_data.json` | 0* | 2026-04-14 23:20 | Exported graph JSON served at `/api/graph` (*single-line JSON file). |
| `./src/web/index.html` | 4,915 | 2026-04-14 14:23:17 | PixiJS + d3-force visualization, X-Ray panel, timeline, AI hooks. |
| `./src/web/timeline_data.json` | 0* | 2026-04-14 23:20 | Timeline JSON served at `/api/timeline` (*minified JSON). |
| `./tests/test_parser.py` | 90 | 2026-04-14 00:08:38 | Unit tests for parser utilities. |
| `./tests/__pycache__/test_parser.cpython-314.pyc` | — | 2026-04-14 | Test bytecode cache. |

\* `wc -l` on minified JSON reports `0` or `1` lines; file size is the meaningful metric (~10.7 MB graph, ~1.8 MB timeline after latest analyze).

## Import Results (Step 2)

| Command | Result |
|---------|--------|
| `from src.parser.python_parser import parse_python` | **FAIL** — `ImportError`: symbol is `parse_python_files`. |
| `from src.parser.typescript_parser import parse_typescript` | **FAIL** — `ImportError`: symbol is `parse_typescript_files`. |
| `from src.parser.dark_matter_parser import parse_dark_matter` | **PASS** |
| `from src.parser.entanglement_parser import parse_entanglements` | **PASS** |
| `from src.parser.git_parser import parse_git_history` | **PASS** |
| `from src.graph.store import GraphStore` | **PASS** |
| `from src.graph.exporter import export_json` | **PASS** |
| `from src.agents.llm_router import LLMRouter` | **PASS** |
| `from src.agents.tools import OmnixTools` | **PASS** |
| `from src.agents.memory import AgentMemory` | **PASS** |
| `from src.agents.orchestrator import AgentOrchestrator` | **PASS** |
| `from src.mcp.server import OmnixMCPServer` | **PASS** |

## Analysis Run (Step 3)

Command: `cd ~/omnix && python omnix.py analyze ~/axiom-control-center`

- **Completes without errors:** **No** — parsing, DB write, and JSON export **succeeded**, then the process **crashed** starting the HTTP server: `OSError: [Errno 98] Address already in use` on `127.0.0.1:7777` (port was occupied at run time).
- **Console output (successful phases):**
  - Timeline: **172** snapshots from **172** commits; date range printed.
  - Parsed: **1223** Python + **277** TypeScript files.
  - **7** dark matter nodes; **100** entangled pairs.
  - **17288** nodes, **36699** edges.
  - AI: **no provider** (`OMNIX_AI_KEY` / Ollama not detected).
- **Dark matter count printed:** Yes (`🌀 7 dark matter nodes detected`).
- **Entanglement count printed:** Yes (`⚡ 100 entangled pairs detected`).
- **Timeline snapshot count printed:** Yes (`⏳ 172 timeline snapshots from 172 commits`).
- **AI agent status printed:** Yes (unavailable message).
- **`omnix.db` created/updated:** Yes (~18 MB SQLite after run).
- **`src/web/graph_data.json` created/updated:** Yes (nodes/links/stats; **17288** / **36699** verified via JSON parse).
- **`src/web/timeline_data.json` created/updated:** Yes (**172** snapshots verified).

## Web Server (Step 4)

**Note:** The exact script you specified uses default **port 7777**. The Step 3 run failed because **7777 was already in use**. For verification, the same flow was exercised on **port 8779** (`analyze` without `--no-open`, background + `sleep 8`).

| Check | Result |
|-------|--------|
| `curl http://127.0.0.1:<port>/` (first 20 lines) | **OK** — HTML document returned (title, Pixi/d3 CDN scripts, styles). |
| `/api/graph` node/link counts | **OK** — `nodes:17288, links:36699`. |
| `/api/timeline` | **OK** — `snapshots:172`. |
| `/api/ai/status` | **OK** — JSON: `available: False`, provider message, `memory_stats` zeros. |

**Step 4 as written (port 7777):** If the port is free, it should behave like the 8779 test; if not, **analyze exits with OSError** and nothing listens on 7777.

## MCP Server (Step 5)

- **`initialize` valid JSON:** **Yes** — single-line JSON-RPC result with `protocolVersion`, `capabilities`, `serverInfo`.
- **`tools/list` returns tools:** **Yes**.
- **Tool count:** **5** (`omnix_search_graph`, `omnix_trace_connections`, `omnix_get_diagnostics`, `omnix_read_file`, `omnix_git_blame`).
- **Stderr:** **None** observed on these runs.

**Note:** The `initialize` request used empty `params` (per your script). Full MCP clients send richer `params`; this server still responds with a valid result for minimal smoke tests.

## Feature Audit (Step 6 — `src/web/index.html`)

Legend: **EXISTS** = implemented logic beyond comments; **STUB** = intentional no-op or placeholder; **MISSING** = not found.

| # | Feature | Verdict | Notes |
|---|---------|---------|-------|
| 1 | Galaxy view with hexagonal directory nodes | **EXISTS** | `drawHexagon`, galaxy model from top directories. |
| 2 | d3-force simulation for layout | **EXISTS** | Galaxy, star, and planet simulations (`d3.forceSimulation`, links, center, charge, collide). |
| 3 | Gravitational hover (cursor proximity expands nodes) | **EXISTS** | `updateGalaxyGravitationalHover`, `GALAXY_WARP_RADIUS`, warp scale. |
| 4 | File orbit dots on hover | **EXISTS** | `childrenGfx` / orbit layout in gravitational hover path. |
| 5 | Sticky hover (grace toward orbit dots) | **EXISTS** | `STICKY_DELAY`, `stickyDir`, `stickyTimeout`. |
| 6 | Left-click hex → star view | **EXISTS** | `onNodeClick` → `transitionToStar`. |
| 7 | Left-click file → planet view | **EXISTS** | Star file `pointerdown` → `transitionToPlanet`. |
| 8 | Right-click blank space → go back one level | **EXISTS** | `onStageUp` button 2 + `isStageBackgroundTarget` → `goBack()` / close X-Ray on galaxy. |
| 9 | Right-click node → X-Ray sidebar | **EXISTS** | `onNodeRightDown` → `openXray` (galaxy directory nodes). |
| 10 | X-Ray: file list with symbol counts | **EXISTS** | `buildXrayHTML` files section with `symbolCount`. |
| 11 | X-Ray: connections (incoming/outgoing/dark) | **EXISTS** | Aggregates `CALLS` / `ENTANGLED` / `DARK_FORCE` etc. |
| 12 | X-Ray: diagnostics (8 rules) | **EXISTS** | `detectIssues`: circular imports, entanglement tiers, dark matter, god file, size, fan-in/out, orphan module (8 rule families). |
| 13 | X-Ray: health bars | **EXISTS** | `buildHealthBar` for complexity, connectivity, entanglement risk. |
| 14 | X-Ray: AI agent section (buttons + input) | **EXISTS** | `buildXrayAiSection` — full UI when `aiAvailable`, otherwise explanatory stub text. |
| 15 | Dark matter toggle + violet nebulae rendering | **EXISTS** | `btn-dark-matter`, `drawDarkMatterOverlay`, violet `nebulaColor`. |
| 16 | Entanglement rendering (amber pulsing curves) | **EXISTS** | `drawEntanglementOverlay`, `0xf59e0b`, pulse. |
| 17 | Timeline slider + scrubber | **EXISTS** | `timeline-slider`, `applyTimelineSnapshot`, panel toggled when data loads. |
| 18 | Signal flow particles along edges | **EXISTS** | `drawSignalFlow`, `SIGNAL_PARTICLES`, galaxy + subviews. |
| 19 | Heartbeat pulse on nodes | **EXISTS** | `applyDirectoryHeartbeatAndGlow` (glow scale/alpha sine). |
| 20 | Ripple rings on hover | **EXISTS** | `drawRippleImpact`, neighbor `_rippleFlashUntil`. |
| 21 | Mycelium edge thickness/color variation | **EXISTS** | Galaxy edges: weight-normalized width, alpha, organic bezier + green/blue lerp (no literal “mycelium” string). |
| 22 | Search/find functionality | **EXISTS** | `search-input`, `runSearchIndex`, dim non-matches, Enter zoom. |
| 23 | Breadcrumb navigation | **EXISTS** | `updateBreadcrumb`, click to galaxy/star. |
| 24 | Stats panel | **EXISTS** | `updateStatsPanel` + overrides for dark matter / entangled from payload. |
| 25 | Fullscreen button | **EXISTS** | `btn-fullscreen` handler. |
| 26 | Export JSON button | **EXISTS** | Fetches `GRAPH_API_URL`, downloads `graph.json`. |
| 27 | FPS counter | **EXISTS** | Ticker updates `#fps-counter`; throttles particle cap by FPS. |
| 28 | Mouse scroll zoom | **EXISTS** | `onWheel` on canvas, `ZOOM_MIN`/`ZOOM_MAX`. |
| 29 | AI trace animation (scanning rings while loading) | **EXISTS** | `startAITraceAnimation` + ticker draws expanding rings on target directory. |
| 30 | AI trace visualization (node flashes when response arrives) | **EXISTS** | `animateAITrace`, `flashNode`, `pulseGalaxyEdgeForTrace`. |

**Additional stub (not in checklist):** `resetGalaxyDrillState()` is an **empty function**; callers exist (e.g. Escape handler) but it currently does nothing.

## Git Status (Step 7)

**Latest commits (`git log --oneline -15`):**
- `aa6507c` v1.3: visual AI reasoning trails  
- `44063dd` v1.2: living force-directed drill-down  
- `ce07f8c` v0.4: spacetime scrubber — git timeline  
- `1871856` v0.3: dark matter + quantum entanglement  
- `7a8af08` v0.2: gravitational hover  
- `2ab63ad` chore: add gitignore  
- `933cc48` v0.1: galaxy view working  

**Working tree:** branch `main`, **up to date with `origin/main`**.

**Uncommitted changes:**
- `omnix.db` — modified (binary)
- `src/mcp/server.py` — modified (~29 insertions, ~15 deletions vs last commit)

**Latest “version” label:** UI shows `OMNIX V0.1` in `index.html`; git HEAD message is **v1.3** — **marketing string lags git tags/messages**.

## Known Bugs (Step 8 — code review)

1. **Port collision ends analyze:** `omnix.py` always binds `--port` (default 7777) after analysis; **EADDRINUSE** aborts the whole process even though graph export already succeeded. No automatic fallback port.
2. **Misleading import names in docs/scripts:** External instructions that use `parse_python` / `parse_typescript` **do not match** the codebase (`parse_python_files` / `parse_typescript_files`).
3. **Empty `resetGalaxyDrillState`:** Called from `loadLevelGalaxy`, Escape handling, and timeline reset; **no state reset** actually occurs — likely dead intent or incomplete refactor.
4. **Right-click star-view file:** Opens X-Ray for the **directory** (`openXrayForDir`), not file-level X-Ray — may surprise users expecting file-scoped panel.
5. **MCP minimal handshake:** Skipping `notifications/initialized` and full MCP param shapes is fine for smoke tests; **real clients** may require stricter sequencing (not validated here).
6. **Analyze + server lifecycle:** If analyze fails at bind, the user may think analyze failed entirely; **DB/JSON are already updated** — confusing UX.
7. **Performance / scale:** ~17k nodes and ~37k edges in JSON — **large payload** for browser; FPS throttling helps but low-end machines may still struggle (design constraint, not a logic bug).
8. **`console.log` in production UI:** e.g. `transitionToPlanet` logs to console — minor cleanliness issue.

## Recommendations (prioritized)

1. **Handle port in use:** Try next free port or print a clear message suggesting `--port` / `--no-open` without traceback; optionally exit 0 after export when bind fails.
2. **Align public API names:** Re-export `parse_python` / `parse_typescript` as aliases, or update all docs/scripts to `parse_*_files`.
3. **Implement or remove `resetGalaxyDrillState`:** Either wire real drill state cleanup or delete calls to avoid false confidence on Escape/timeline.
4. **Sync version string:** Update `#omnix-version` in `index.html` to match released git version (or drive it from a single source).
5. **Commit or revert:** Decide whether `omnix.db` and `src/mcp/server.py` changes should be committed or kept local; `.gitignore` for DB if it should not be versioned.
6. **Document AI keys:** README already hints; add explicit “analyze completes without AI” vs “web AI features” matrix to reduce support friction.

---

*Audit performed in the workspace environment: analyze run and HTTP checks executed against `/home/harsh/axiom-control-center` where present. Step 4 duplicated on port **8779** when default port was unavailable.*
