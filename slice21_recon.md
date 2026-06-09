# Slice-21 Recon Manifest

### Outer tab strip
- Component: `src/studio/frontend/src/components/Workspace.tsx`
- Tab definition: `rightTabs: RightPanelTab[]` in `Workspace.tsx`
  - Current right panel tab ids/labels:
    - `id: "xray", label: "X-Ray"` (the slice-21 rename target)
    - `id: "code", label: "Code"`
    - `id: "history", label: "History"`
  - Evidence:
    - `Workspace.tsx` defines the array and passes it to `<RightPanel tabs={rightTabs} activeTab={rightTab} ... />`
- Active state: local React state in `Workspace.tsx`
  - `const [rightTab, setRightTab] = useState<RightPanelTabId>("xray");`
  - `setRightTab("xray")` is also used when selecting an entity (`selectXRayNode`) and in `openXRayFileOrDir`.
- "X-RAY" string location:
  - **Outer label** is `"X-Ray"` in `Workspace.tsx` (`rightTabs` entry for id `"xray"`).
  - The header label inside the inspector is already `"BRAIN"` (see `XRayHead.tsx`).

### Inner inspector tabs
- Component: `src/studio/frontend/src/components/XRayItabs.tsx`
- Tab definition:
  - `export type XRayInnerTab = "code" | "agent" | "diagnostics" | "history";`
  - `const TABS = [{ id: "code", label: "Code" }, { id: "agent", label: "Agent" }, { id: "diagnostics", label: "Diagnostics" }, { id: "history", label: "History" }]`
  - `XRayTab` owns the active inner tab state: `useState<XRayInnerTab>("code")`.
- Current 4 tabs: CODE / AGENT / DIAGNOSTICS / HISTORY
  - Defined in `XRayItabs.tsx` lines 1–13 (see file read in Phase 0).
- Empty-state copy (relevant to behavior preservation):
  - In `XRayContent.tsx` (active `"code"` path), with no symbol selected:
    - “Select a function or class in the constellation to load source in this tab.”
  - `active === "history"` currently renders a message that history lives in the outer History panel tab (right rail), not inside the inspector.
  - `active === "agent"` currently renders “Quick actions” buttons (NOT a feed).
  - `active === "diagnostics"` currently renders diagnostics health/issues list.

### WebSocket client
- Location:
  - Client implementation: `src/studio/frontend/src/lib/ws.ts` (`StudioWebSocket`)
  - Wiring + message ingestion: `src/studio/frontend/src/components/Workspace.tsx`
  - Server protocol types reference: `src/studio/ws_protocol.py` (`ALL_SERVER_TYPES`)
- Connection: `Workspace.tsx` creates `new StudioWebSocket(workspaceId, onMessage, onState, onCloseCode)` inside a `useEffect`, then calls `connect()`.
  - Subscription handshake happens in `StudioWebSocket` `onopen`: sends JSON `{ type: "subscribe", workspace_id }`.
  - Heartbeat: sends JSON `{ type: "ping", ts: performance.now()/1000 }` on an interval.
- Subscription API: there is **no topic-based subscribe** on the client; `Workspace.tsx` receives all messages and routes by `msg.type`.
  - `Workspace.tsx` parses `kind = typeof msg.type === "string" ? msg.type : ""` and handles:
    - `node_added` (updates `graphNodes`)
    - `edge_added` (updates `graphEdges`)
    - `edge_removed`
    - `node_modified` (applies `applyNodeModified`)
    - `node_removed`
    - `file_added` / `file_removed` (touches code epoch)
  - It also forwards the raw message to `graphRef.current?.ingestMessage(msg)` (GraphCanvas) before/alongside local state updates.
- Reconnect logic: **yes**
  - `StudioWebSocket` reconnects with exponential backoff (up to `MAX_BACKOFF_MS = 30_000`) on close.
  - `Workspace.tsx` tracks reconnect UX via `hasConnectedBeforeRef` and `reconnectedPhase`.

### Receipt files
- Receipt cache location on disk:
  - `~/.omnix/receipts/` exists (observed via `ls -la ~/.omnix/` which showed `receipts/`).
- Receipt formats found:
  - Backend route `_iter_receipts()` currently enumerates **only** `~/.omnix/receipts/*.json` and checks for a detached signature at `*.sig`.
  - The audit notes additional receipt subtrees (e.g. findings receipts under `~/.omnix/receipts/findings/<project_id>/...`) used by `/api/findings/scans`.
- Existing /api endpoint that returns receipts? **YES**
  - `GET /api/workspace/{workspace_id}/receipts` returns `{ receipts: ReceiptEntry[] }` (see `server.py` around the `@app.get("/api/workspace/{workspace_id}/receipts")` route).
  - `GET /api/workspace/{workspace_id}/receipts/{receipt_id}` returns `{ receipt: {...} }`.
  - Frontend already consumes this via `listReceipts(workspaceId, ...)` in `src/studio/frontend/src/lib/api.ts`.
  - There is also a separate localhost-only verifier endpoint: `POST /api/grammar/verify-receipt` that shells out to `omnix axiom verify ...` (not required for slice-21; noted for governance surfaces).
- Phase 4 expectation from recon:
  - Phase 4 **Plan A** is available: reuse existing `/api/workspace/{workspace_id}/receipts` (no backend changes needed).
  - Important limitation: `_iter_receipts()` only scans `~/.omnix/receipts/*.json` (top-level). If the receipts we want live elsewhere, Phase 4 must decide whether to expand enumeration (scope risk) or show empty state / partial list.

### Test infrastructure
- Existing right-panel/inspector test files:
  - `src/studio/frontend/src/components/__tests__/test_xray_tab.test.tsx` (covers `XRayTab`, inner tabs, and uses a WS + API harness)
  - `src/studio/frontend/src/components/__tests__/test_resize_collapse.test.tsx` (covers `RightPanel`)
  - `src/studio/frontend/src/components/__tests__/test_slice14_shell_components.test.tsx` (includes `RightPanel` and `ReceiptsDrawer` interactions)
  - Naming-string assertions: `src/studio/frontend/src/components/__tests__/naming-pivot.test.tsx`
- Test framework: **vitest** (confirmed by imports + package.json audit)
- Mocking patterns for WebSocket:
  - `vi.mock("@/lib/ws", ...)` is used broadly; a harness captures the WS `onMessage` callback and can `emit()` synthetic messages (see `test_xray_tab.test.tsx`).
  - This is a strong base for Phase 3 (AGENT feed) reconnect tests too.

### Ruflo output (or ripgrep fallback)
- Tooling note: `rg` is not available in this environment (`bash: rg: command not found`), so Phase 0 used Cursor search instead of shell `rg`.
- analyze symbols:
  - Ruflo successfully scanned components and reported `Files scanned: 74` and “… and 323 more symbols”.
- analyze imports:
  - Top imports include `react`, `vitest`, and local modules like `../StudioGraph`, `./XRayItabs`, `@/lib/xray_diagnostics`, `@/store/studioScopeStore`.
- analyze boundaries:
  - Reported a minimal cut with `vite-env.d.ts` isolated; otherwise one main partition (no actionable boundary alarm for slice-21).
- Ruflo errno -122 hit? **No**

---

## Phase 6 verification notes (post-implementation)

- **Build**: `npm run build` succeeded (tsc --noEmit + vite build).
- **dist mtime**: `src/studio/frontend/dist/index.html` updated at `2026-05-05 02:45:10 -0700`.
- **HTTP smoke**:
  - `/` returned **200** on `127.0.0.1:7777`.
  - `/api/workspace/<id>/receipts` requires a real workspace id; probing with `"test"` returns `{"detail":"unknown workspace_id"}` as expected.
- **Backend Python diff**: none (Phase 4 locked to Plan A).

## OBSERVED notes

- **Receipts enumeration**: current backend receipt listing scans **top-level** `~/.omnix/receipts/*.json` only; the `findings/<project_id>/` subtree is not enumerated by `_iter_receipts()` (separate hygiene slice).
- **History persistence**: inner HISTORY feed is session-scoped (wire-event buffer). True persistent history requires a backend mutation log or DB-backed `/api/history` (deferred).

