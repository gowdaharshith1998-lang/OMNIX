import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { GraphCanvas, type GraphCanvasHandle } from "../Graph/GraphCanvas";
import { ConstellationBoundary } from "../ConstellationBoundary";
import { BugsDrawer } from "../drawers/BugsDrawer";
import { FilesDrawer } from "../drawers/FilesDrawer";
import { GrammarHealthDrawer } from "../drawers/GrammarHealthDrawer";
import { ReceiptsDrawer } from "../drawers/ReceiptsDrawer";
import { SearchDrawer } from "../drawers/SearchDrawer";
import { SettingsDrawer } from "../drawers/SettingsDrawer";
import { FindBar } from "../FindBar";
import {
  listReceipts,
  type BugFinding,
  type BugScanSummary,
  type BugsScanEvent,
  type SearchResult,
} from "@/lib/api";
import { isT1Mode } from "@/lib/t1Mode";
import { StudioWebSocket } from "@/lib/ws";
import { pushWireEvent } from "@/lib/wireEventBuffer";
import type { WireEvent, WireEventType } from "@/components/inspector/AgentTab";
import {
  applyNodeModified,
  recordEdgeFromGraphPayload,
  recordFromGraphPayload,
} from "@/lib/graphNode";
import type {
  ScopeNavigationSpec,
  ScopeVisualEmptyDetail,
  ViewerScopePayload,
} from "../Graph/StudioGraph";
import type { GraphEdge, GraphNode } from "@/types/drilldown";
import {
  ancestryChain,
  CANONICAL_SCOPES,
  computeScopedStats,
  extendRegistryWithGraphNodes,
  scopeRecordsToMaps,
  type ScopeRecord,
} from "@/store/scopeRegistry";
import {
  configureStudioScopeHandlers,
  getStudioScopeSnapshot,
  setScope,
  setSelectedNode,
  setValidScopeIds,
  syncScopeFromViewer,
  useScope,
} from "@/store/studioScopeStore";
import { TopBar } from "./TopBar";
import { LeftRail, type LeftRailIcon } from "./LeftRail";
import { Inspector } from "./Inspector";
import { XRayTabContent } from "./XRayTabContent";
import { ChatTab } from "./ChatTab";
import { InspectorHistoryTab } from "./InspectorHistoryTab";
import { InspectorReceiptsTab, type ReceiptEntry as M42Receipt } from "./InspectorReceiptsTab";
import { BottomBar } from "./BottomBar";
import { DecisionModal } from "./DecisionModal";
import { CutoverModal } from "./CutoverModal";
import { SlideSettingsDrawer } from "./SlideSettingsDrawer";
import { SplitGraphContainer } from "./SplitGraphContainer";
import type {
  ChatMessage,
  DecisionPayload,
  GraphSide,
  RightTabId,
  RunState,
} from "./types";

type Props = {
  workspaceId: string;
  projectPath: string;
  initialStats: {
    files: number;
    functions: number;
    classes: number;
    edges: number;
  };
  onBack: () => void;
};

type WsState = "idle" | "connecting" | "open" | "closed";

function projectLabel(p: string) {
  const s = p.replace(/\\/g, "/");
  const parts = s.split("/").filter(Boolean);
  return parts.length > 0 ? (parts[parts.length - 1] as string) : s;
}

function navigationSpecForScopeRecord(
  id: string,
  byId: Map<string, ScopeRecord>
): ScopeNavigationSpec {
  const r = byId.get(id);
  if (!r || id === "repo") return { kind: "repo" };
  if (r.badge === "FILE" && r.pathPrefix)
    return { kind: "file", path: r.pathPrefix };
  if (r.pathPrefix) return { kind: "directory", path: r.pathPrefix };
  return { kind: "repo" };
}

function scopeIdFromViewerPayload(
  payload: ViewerScopePayload,
  pathToId: Map<string, string>
): string {
  if (payload.kind === "repo") return "repo";
  const path = payload.path.replace(/\\/g, "/");
  const direct = pathToId.get(path);
  if (direct) return direct;
  let best: { len: number; id: string } | null = null;
  for (const [prefix, scopeId] of pathToId) {
    if (!prefix) continue;
    if (path === prefix || path.startsWith(`${prefix}/`)) {
      if (!best || prefix.length > best.len) {
        best = { len: prefix.length, id: scopeId };
      }
    }
  }
  return best?.id ?? "repo";
}

function isBugsScanEvent(msg: Record<string, unknown>): msg is BugsScanEvent {
  return (
    msg.type === "bugs_scan_started" ||
    msg.type === "bugs_scan_heartbeat" ||
    msg.type === "bugs_scan_complete" ||
    msg.type === "bugs_scan_error"
  );
}

function welcomeMessage(): ChatMessage {
  return {
    id: "agent:welcome",
    role: "agent",
    ts: Date.now(),
    text:
      "Welcome to OMNIX Studio. I've indexed this workspace. Pick a target in the bottom bar, then choose one of these to begin — or message me directly.",
    actions: [
      { id: "start_modernization", label: "Start modernization" },
      { id: "deep_analyze", label: "Deep analyze" },
      { id: "find_bugs", label: "Find bugs first" },
    ],
  };
}

function defaultDecision(symbol: string): DecisionPayload {
  return {
    gate: "gate 3 of 6",
    symbol,
    question:
      "couldn't equivalence-match the rebuilt method to the legacy implementation. How should I proceed?",
    options: [
      {
        id: "tighten_property",
        title: "Tighten the property test to cover the divergence",
        hint: "Most common — increases gate coverage but stays automated.",
        recommended: true,
      },
      {
        id: "accept_known_diff",
        title: "Accept the difference (known legacy quirk)",
        hint: "Annotates it in the receipt; ships with a quirk note.",
      },
      {
        id: "rebuild_method",
        title: "Re-attempt rebuild with stricter prompt",
        hint: "Burns a few seconds of compute; usually closes the gap.",
      },
    ],
  };
}

function shortHash(input: string): string {
  let h = 0;
  for (let i = 0; i < input.length; i += 1) h = (h * 31 + input.charCodeAt(i)) | 0;
  const hex = (h >>> 0).toString(16);
  return hex.padStart(8, "0").slice(0, 7);
}

const DRAWER_LABELS: Record<LeftRailIcon, string> = {
  files: "Files",
  search: "Search",
  bugs: "Bugs",
  receipts: "Receipts",
  grammar: "Grammar Health",
  settings: "Settings",
};

export function M42Workspace({
  workspaceId,
  projectPath,
  initialStats,
  onBack,
}: Props) {
  const [runState, setRunState] = useState<RunState>("idle");
  const [progressPct, setProgressPct] = useState(0);
  const [etaSec, setEtaSec] = useState<number | null>(null);
  const [currentSymbol, setCurrentSymbol] = useState<string | null>(null);
  const [doneSummary, setDoneSummary] = useState<string | null>(null);
  const [doneReceiptHash, setDoneReceiptHash] = useState<string | null>(null);
  const [decisionPayload, setDecisionPayload] = useState<DecisionPayload | null>(null);
  const [decisionOpen, setDecisionOpen] = useState(false);
  // Cutover modal — Shape B v2. Trigger surface lives in the XRay node action menu;
  // the modal mount is additive here so existing modal infrastructure is untouched.
  const [cutoverUnit, setCutoverUnit] = useState<string | null>(null);

  const [sourceLang, setSourceLang] = useState("auto");
  const [targetLang, setTargetLang] = useState("java21");
  const [model, setModel] = useState("Opus 4.7");

  const [leftRailCollapsed, setLeftRailCollapsed] = useState(true);
  const [inspectorCollapsed, setInspectorCollapsed] = useState(false);
  const [activeDrawer, setActiveDrawer] = useState<LeftRailIcon | null>(null);
  const [rightTab, setRightTab] = useState<RightTabId>("xray");
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [settingsSection, setSettingsSection] = useState("account");
  const [find, setFind] = useState("");

  const [chatMessages, setChatMessages] = useState<ChatMessage[]>([welcomeMessage()]);
  const [historyEvents, setHistoryEvents] = useState<WireEvent[]>([]);
  const [receipts, setReceipts] = useState<M42Receipt[]>([]);
  const receiptsLoadedRef = useRef(false);

  const [wsState, setWsState] = useState<WsState>("idle");
  const [bugsScanEvent, setBugsScanEvent] = useState<BugsScanEvent | null>(null);
  const [bugsScanFindings, setBugsScanFindings] = useState<BugFinding[]>([]);
  const [bugsScanSummary, setBugsScanSummary] = useState<BugScanSummary | null>(null);

  const [graphNodes, setGraphNodes] = useState<Map<string, GraphNode>>(() => new Map());
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);
  const [scopeRecords, setScopeRecords] = useState<ScopeRecord[]>(CANONICAL_SCOPES);
  const [, setEmptyScopeOverlay] = useState<ScopeVisualEmptyDetail | null>(null);
  const [constellationMountEpoch] = useState(0);
  const [graphSide, setGraphSide] = useState<GraphSide>("source");

  const graphRef = useRef<GraphCanvasHandle | null>(null);
  const graphNodesRef = useRef(graphNodes);
  graphNodesRef.current = graphNodes;

  const { currentScope, selectedNodeId } = useScope();
  const scopeMaps = useMemo(() => scopeRecordsToMaps(scopeRecords), [scopeRecords]);
  const scopeById = scopeMaps.byId;
  const pathToScopeId = scopeMaps.pathToId;
  const pathToScopeIdRef = useRef(pathToScopeId);
  pathToScopeIdRef.current = pathToScopeId;
  const scopeByIdRef = useRef(scopeById);
  scopeByIdRef.current = scopeById;

  const nodesList = useMemo(() => Array.from(graphNodes.values()), [graphNodes]);

  const displayStats = useMemo(() => {
    const rec = scopeById.get(currentScope);
    const prefix = rec?.pathPrefix ?? null;
    if (currentScope === "repo" && graphNodes.size === 0) {
      return {
        files: initialStats.files,
        functions: initialStats.functions,
        classes: initialStats.classes,
        edges: initialStats.edges,
      };
    }
    const m = computeScopedStats(nodesList, graphEdges, prefix);
    return {
      files: m.files,
      functions: m.functions,
      classes: m.classes,
      edges: m.edges,
    };
  }, [
    currentScope,
    graphEdges,
    graphNodes.size,
    initialStats.classes,
    initialStats.edges,
    initialStats.files,
    initialStats.functions,
    nodesList,
    scopeById,
  ]);

  const navigationSpec = useMemo(
    () => navigationSpecForScopeRecord(currentScope, scopeById),
    [currentScope, scopeById]
  );

  const indexedCommit = useMemo(() => shortHash(projectPath), [projectPath]);
  const workspaceName = useMemo(() => projectLabel(projectPath), [projectPath]);

  const pushAgent = useCallback((text: string, actions?: ChatMessage["actions"]) => {
    setChatMessages((prev) => [
      ...prev,
      { id: `agent:${Date.now()}-${prev.length}`, role: "agent", ts: Date.now(), text, actions },
    ]);
  }, []);

  const pushSystem = useCallback((text: string) => {
    setChatMessages((prev) => [
      ...prev,
      { id: `sys:${Date.now()}-${prev.length}`, role: "system", ts: Date.now(), text },
    ]);
  }, []);

  useEffect(() => {
    configureStudioScopeHandlers({
      onInvalidScope: () => {
        /* swallow — non-fatal in M4.2 chrome */
      },
    });
  }, []);

  useEffect(() => {
    const allow =
      import.meta.env.DEV || import.meta.env.VITE_OMNIX_STUDIO_DEBUG === "1";
    if (!allow && new URLSearchParams(window.location.search).get("debug") !== "1") {
      return;
    }
    const w = window as unknown as {
      __m42_open_decision?: (symbol?: string) => void;
      __m42_set_run?: (state: RunState) => void;
    };
    w.__m42_open_decision = (symbol) => {
      setDecisionPayload(
        defaultDecision(symbol ?? currentSymbol ?? "CustomerService.calculate_premium")
      );
      setDecisionOpen(true);
      setRunState("decision");
    };
    w.__m42_set_run = (state) => setRunState(state);
    return () => {
      delete w.__m42_open_decision;
      delete w.__m42_set_run;
    };
  }, [currentSymbol]);

  useEffect(() => {
    if (graphNodes.size === 0) {
      setScopeRecords(CANONICAL_SCOPES);
      setValidScopeIds(CANONICAL_SCOPES.map((r) => r.id));
      return;
    }
    const extended = extendRegistryWithGraphNodes(
      CANONICAL_SCOPES,
      graphNodes.values()
    );
    setScopeRecords(extended);
    setValidScopeIds(extended.map((r) => r.id));
  }, [graphNodes]);

  const onViewerScope = useCallback((payload: ViewerScopePayload) => {
    const id = scopeIdFromViewerPayload(payload, pathToScopeIdRef.current);
    syncScopeFromViewer(id, {
      pathPrefixForScope: (sid) => scopeByIdRef.current.get(sid)?.pathPrefix ?? null,
      selectedFilePath: () => {
        const sid = getStudioScopeSnapshot().selectedNodeId;
        return sid ? graphNodesRef.current.get(sid)?.file_path ?? null : null;
      },
    });
  }, []);

  const onScopeVisualEmpty = useCallback((detail: ScopeVisualEmptyDetail | null) => {
    setEmptyScopeOverlay(detail);
  }, []);

  const ingestWorkspaceMessage = useCallback(
    (msg: Record<string, unknown>) => {
      const kind = typeof msg.type === "string" ? msg.type : "";
      const tsRaw = (msg as { ts?: unknown }).ts;
      const ts =
        typeof tsRaw === "number"
          ? tsRaw < 1_000_000_000_000
            ? tsRaw * 1000
            : tsRaw
          : Date.now();
      const log = (t: WireEventType, targetId: string) => {
        const event = {
          id: `${t}:${targetId}:${ts}`,
          type: t,
          ts,
          actor: null,
          targetId,
          targetType: "code",
          confidence: null,
        };
        pushWireEvent(workspaceId, event);
        setHistoryEvents((prev) => [event, ...prev].slice(0, 500));
      };

      if (kind === "node_added" && msg.node && typeof msg.node === "object") {
        const rec = recordFromGraphPayload(msg.node as Record<string, unknown>);
        if (rec) {
          setGraphNodes((prev) => {
            const next = new Map(prev);
            next.set(rec.id, rec);
            return next;
          });
          log("node_added", rec.id);
        }
        return;
      }
      if (kind === "edge_added" && msg.edge && typeof msg.edge === "object") {
        const rec = recordEdgeFromGraphPayload(msg.edge as Record<string, unknown>);
        if (rec) {
          setGraphEdges((prev) => {
            if (prev.some((edge) => String(edge.id) === String(rec.id))) return prev;
            return [...prev, rec];
          });
          log("edge_added", String(rec.id));
        }
        return;
      }
      if (kind === "edge_removed" && msg.edge_id != null) {
        const id = String(msg.edge_id);
        setGraphEdges((prev) => prev.filter((edge) => String(edge.id) !== id));
        log("edge_removed", id);
        return;
      }
      if (kind === "node_modified" && typeof msg.node_id === "string") {
        const prevNode = graphNodesRef.current.get(msg.node_id);
        if (prevNode) {
          const changes =
            msg.changes && typeof msg.changes === "object"
              ? (msg.changes as Parameters<typeof applyNodeModified>[1])
              : undefined;
          const nextNode = applyNodeModified(prevNode, changes);
          setGraphNodes((prev) => {
            const next = new Map(prev);
            next.set(nextNode.id, nextNode);
            return next;
          });
          log("node_modified", nextNode.id);
        }
        return;
      }
      if (kind === "node_removed" && typeof msg.node_id === "string") {
        setGraphNodes((prev) => {
          const next = new Map(prev);
          next.delete(msg.node_id as string);
          return next;
        });
        log("node_removed", msg.node_id);
        return;
      }
      if (kind === "node_replicated" && typeof msg.symbol === "string") {
        pushAgent(`Replicated ${msg.symbol} · gates 0–${msg.gates ?? 6} ✓`);
        return;
      }
      if (kind === "gate_failed" && typeof msg.symbol === "string") {
        const payload = defaultDecision(String(msg.symbol));
        setDecisionPayload(payload);
        setDecisionOpen(true);
        setRunState("decision");
        pushAgent(`Hit a problem on ${msg.symbol}`, [
          { id: "open_decision", label: "Open decision" },
        ]);
        return;
      }
      if (kind === "run_started") {
        pushAgent(
          `Started modernization. Source ${String(msg.source ?? "—")} → target ${String(msg.target ?? targetLang)}`
        );
        setRunState("running");
        return;
      }
      if (kind === "run_complete") {
        const methods = Number(msg.methods ?? 0);
        const equivalence = Number(msg.equivalence ?? 0);
        pushAgent(`Complete. ${methods} methods, ${equivalence}% equivalence.`);
        setRunState("done");
        setProgressPct(100);
        setDoneSummary(`${methods} methods · ${equivalence}% equivalence`);
        setDoneReceiptHash(shortHash(`run:${methods}:${equivalence}:${Date.now()}`));
        return;
      }
    },
    [pushAgent, targetLang, workspaceId]
  );

  useEffect(() => {
    if (isT1Mode()) return;
    const ws = new StudioWebSocket(
      workspaceId,
      (msg) => {
        const m = msg as Record<string, unknown>;
        if (isBugsScanEvent(m)) {
          setBugsScanEvent(m);
          if (m.type === "bugs_scan_complete") {
            setBugsScanFindings(m.findings);
            setBugsScanSummary(m.summary);
          }
        }
        graphRef.current?.ingestMessage(msg);
        ingestWorkspaceMessage(m);
      },
      (s) => {
        if (s === "connecting") setWsState("connecting");
        if (s === "open") setWsState("open");
        if (s === "closed") setWsState("closed");
      }
    );
    ws.connect();
    return () => ws.close();
  }, [ingestWorkspaceMessage, workspaceId]);

  const fetchReceipts = useCallback(async () => {
    try {
      const rows = await listReceipts(workspaceId, { limit: 100 });
      const mapped: M42Receipt[] = rows.map((r) => ({
        id: r.receipt_id || r.hash_prefix || r.path,
        label: `${r.kind} · ${r.target}`,
        ts: new Date(r.mtime_iso).getTime() || Date.now(),
        hashShort: (r.hash_prefix || "").slice(0, 7) || "—",
        verified: r.has_signature ? (r.verified ?? null) : null,
      }));
      setReceipts(mapped);
    } catch {
      setReceipts([]);
    }
  }, [workspaceId]);

  useEffect(() => {
    if (rightTab === "receipts" && !receiptsLoadedRef.current) {
      receiptsLoadedRef.current = true;
      void fetchReceipts();
    }
  }, [fetchReceipts, rightTab]);

  const isReposScope = currentScope === "repo";

  const onChatSend = useCallback(
    (text: string) => {
      setChatMessages((prev) => [
        ...prev,
        { id: `user:${Date.now()}-${prev.length}`, role: "user", ts: Date.now(), text },
      ]);
      const lower = text.toLowerCase();
      if (lower.includes("start") && lower.includes("modern")) {
        pushAgent("Starting modernization run. Watch the graph split.", [
          { id: "pause", label: "Pause" },
        ]);
        setRunState("running");
        return;
      }
      pushAgent(
        "I heard you. Real model routing is wired through the model picker — currently no provider key is set, so I'm only echoing. Pick a target language and hit Start to see the run state."
      );
    },
    [pushAgent]
  );

  const onChatAction = useCallback(
    (_messageId: string, actionId: string) => {
      if (actionId === "start_modernization") {
        pushAgent("Starting modernization run. Watch the graph split.");
        setRunState("running");
        setProgressPct(8);
        setEtaSec(180);
        setCurrentSymbol("CustomerService.calculate_premium");
        return;
      }
      if (actionId === "deep_analyze") {
        pushAgent("Deep analysis kicked off — running gate-3 property probes across the indexed graph.");
        return;
      }
      if (actionId === "find_bugs") {
        pushAgent("Running the bug scanner over this workspace. You can also open the Bugs drawer to follow live.");
        setActiveDrawer("bugs");
        setLeftRailCollapsed(false);
        return;
      }
      if (actionId === "open_decision") {
        setDecisionOpen(true);
        return;
      }
      if (actionId === "pause") {
        setRunState("idle");
        pushSystem("Run paused (stub — orchestrator pause endpoint not wired).");
        return;
      }
      pushSystem(`Action "${actionId}" — endpoint not wired yet.`);
    },
    [pushAgent, pushSystem]
  );

  useEffect(() => {
    if (runState !== "running") return;
    const timer = window.setInterval(() => {
      setProgressPct((p) => {
        const next = Math.min(100, p + 1.5);
        if (next >= 100) {
          setRunState("done");
          setDoneSummary("12 methods · 96% equivalence");
          setDoneReceiptHash(shortHash(`auto:${Date.now()}`));
          setCurrentSymbol(null);
          setEtaSec(null);
          pushAgent("Complete. 12 methods, 96% equivalence.");
        }
        return next;
      });
      setEtaSec((sec) => (sec == null ? null : Math.max(0, sec - 1.5)));
    }, 250);
    return () => window.clearInterval(timer);
  }, [pushAgent, runState]);

  const selectLeftRailIcon = (icon: LeftRailIcon) => {
    if (icon === "settings") {
      setSettingsOpen(true);
      return;
    }
    if (activeDrawer === icon) {
      setActiveDrawer(null);
      return;
    }
    setActiveDrawer(icon);
    setLeftRailCollapsed(false);
  };

  const inspectorContent: ReactNode = (() => {
    if (rightTab === "xray") {
      const rec = scopeById.get(currentScope);
      const kind: "Repository" | "Module" | "File" | "Symbol" =
        currentScope === "repo"
          ? "Repository"
          : selectedNodeId
            ? "Symbol"
            : rec?.badge === "FILE"
              ? "File"
              : "Module";
      const label =
        currentScope === "repo"
          ? workspaceName
          : rec?.label ?? currentScope;
      const path = currentScope === "repo" ? projectPath : rec?.pathPrefix ?? "";
      const diagnostics = bugsScanSummary
        ? [
            {
              id: "bugs-total",
              title: `${bugsScanFindings.length} potential issue${bugsScanFindings.length === 1 ? "" : "s"} found`,
              hint: bugsScanFindings.length > 0 ? "Open the Bugs drawer to triage." : undefined,
            },
          ]
        : undefined;
      return (
        <XRayTabContent
          side={graphSide}
          scopeKind={kind}
          scopeLabel={label}
          scopePath={path}
          stats={displayStats}
          diagnostics={diagnostics}
          onTargetAction={(action) => {
            pushSystem(
              action === "source"
                ? "Generated source view lands when the run completes."
                : action === "receipt"
                  ? "Receipt view will mount the signed JSON from .omnix/receipts/."
                  : "Side-by-side diff will mount once target codebase materializes."
            );
          }}
        />
      );
    }
    if (rightTab === "chat") {
      return <ChatTab messages={chatMessages} onSend={onChatSend} onAction={onChatAction} />;
    }
    if (rightTab === "receipts") {
      return (
        <InspectorReceiptsTab
          receipts={receipts}
          onRefresh={fetchReceipts}
          onVerify={(_id) => {
            return true;
          }}
        />
      );
    }
    return <InspectorHistoryTab events={historyEvents} />;
  })();

  const renderGraph = (mode: "source" | "target"): ReactNode => {
    if (mode === "target") {
      const replicated = Math.max(0, Math.floor((progressPct / 100) * (graphNodes.size || 32)));
      const remaining = Math.max(0, (graphNodes.size || 32) - replicated);
      return (
        <div
          style={{
            position: "absolute",
            inset: 0,
            display: "flex",
            flexDirection: "column",
            alignItems: "center",
            justifyContent: "center",
            color: "var(--m42-text-tertiary)",
            fontFamily: "var(--omnix-font-mono)",
            fontSize: 11,
            gap: 8,
            padding: 24,
            textAlign: "center",
          }}
        >
          <div style={{ fontSize: 12, color: "var(--m42-text-secondary)" }}>
            target codebase materializing
          </div>
          <div>
            {replicated} done · {remaining} pending
          </div>
          <div
            style={{
              display: "grid",
              gridTemplateColumns: "repeat(8, 12px)",
              gap: 6,
              marginTop: 12,
            }}
          >
            {Array.from({ length: Math.min(64, replicated + remaining) }).map((_, i) => (
              <span
                key={i}
                style={{
                  width: 12,
                  height: 12,
                  borderRadius: 2,
                  background:
                    i < replicated
                      ? "var(--m42-status-success)"
                      : "var(--m42-bg-2)",
                  border: `0.5px solid ${i < replicated ? "var(--m42-status-success)" : "var(--m42-border)"}`,
                  opacity: i < replicated ? 0.9 : 0.5,
                }}
              />
            ))}
          </div>
        </div>
      );
    }
    return (
      <ConstellationBoundary onRetry={() => undefined}>
        <GraphCanvas
          key={`m42-${constellationMountEpoch}`}
          ref={graphRef}
          drillDownNodeId={null}
          navigationSpec={navigationSpec}
          onFunctionNodeClick={(nodeId) => {
            setSelectedNode(nodeId);
            setGraphSide("source");
            setRightTab("xray");
            setInspectorCollapsed(false);
          }}
          onT1GraphNodes={(list) => {
            setGraphNodes((prev) => {
              const next = new Map(prev);
              for (const n of list) next.set(n.id, n);
              return next;
            });
          }}
          onT1GraphEdges={(list) => setGraphEdges(list)}
          onFileOrDirClick={() => {
            setGraphSide("source");
            setRightTab("xray");
            setInspectorCollapsed(false);
          }}
          onDeselect={() => setSelectedNode(null)}
          onNavigationStateChange={() => undefined}
          onViewerScope={onViewerScope}
          onScopeVisualEmpty={onScopeVisualEmpty}
        />
      </ConstellationBoundary>
    );
  };

  const onStart = () => {
    setRunState("running");
    setProgressPct(4);
    setEtaSec(180);
    setCurrentSymbol("CustomerService.calculate_premium");
    setGraphSide("source");
    pushAgent(`Run started. Source ${sourceLang} → target ${targetLang}.`);
  };

  const settingsSections = useMemo(
    () => [
      {
        id: "account",
        label: "Account",
        render: () => (
          <div style={{ display: "flex", flexDirection: "column", gap: 12 }}>
            <div className="m42-xray-card">
              <div style={{ fontSize: 12 }}>{workspaceName}</div>
              <div className="m42-card-hint">{projectPath}</div>
            </div>
            <button type="button" className="m42-btn" onClick={onBack}>
              Switch workspace
            </button>
          </div>
        ),
      },
      {
        id: "vault",
        label: "Vault",
        render: () => (
          <div className="m42-xray-card" style={{ color: "var(--m42-text-tertiary)" }}>
            Vault session controls live in the Files / Settings drawer for now.
          </div>
        ),
      },
      {
        id: "keys",
        label: "Provider keys",
        render: () => (
          <SettingsDrawer projectPath={projectPath} />
        ),
      },
      {
        id: "model",
        label: "Model",
        render: () => (
          <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
            <div className="m42-xray-card">
              <div style={{ fontSize: 12 }}>Active</div>
              <div className="m42-card-hint">{model}</div>
            </div>
            <div className="m42-xray-card" style={{ color: "var(--m42-text-tertiary)" }}>
              Switch via the top-bar model picker.
            </div>
          </div>
        ),
      },
    ],
    [model, onBack, projectPath, workspaceName]
  );

  const crumbChain = ancestryChain(currentScope, scopeById);

  return (
    <div
      className="m42-shell"
      data-run-state={runState}
      data-testid="m42-shell"
    >
      <TopBar
        workspaceLabel={workspaceName}
        workspacePath={projectPath}
        indexedCommit={indexedCommit}
        status={
          wsState === "open"
            ? "connected"
            : wsState === "connecting" || wsState === "idle"
              ? "connecting"
              : "closed"
        }
        model={model}
        onChangeModel={setModel}
        onOpenSettings={() => setSettingsOpen(true)}
        userInitial={workspaceName.charAt(0).toUpperCase() || "O"}
      />

      <div className="m42-shell-body">
        <LeftRail
          active={activeDrawer}
          collapsed={leftRailCollapsed}
          onToggleCollapsed={() => setLeftRailCollapsed((s) => !s)}
          onSelect={selectLeftRailIcon}
        />
        {activeDrawer ? (
          <aside
            className="m42-leftdrawer"
            aria-label={`${DRAWER_LABELS[activeDrawer]} drawer`}
            data-testid="m42-leftdrawer"
          >
            <div className="m42-drawer-head">
              <span>{DRAWER_LABELS[activeDrawer]}</span>
              <button
                type="button"
                className="m42-iconbtn"
                aria-label="Close drawer"
                onClick={() => setActiveDrawer(null)}
              >
                ✕
              </button>
            </div>
            <div className="m42-drawer-body">
              {activeDrawer === "files" ? (
                <FilesDrawer
                  workspaceId={workspaceId}
                  onOpenFile={() => {
                    setRightTab("xray");
                    setInspectorCollapsed(false);
                  }}
                />
              ) : null}
              {activeDrawer === "search" ? (
                <SearchDrawer
                  workspaceId={workspaceId}
                  query={find}
                  fallbackNodes={nodesList}
                  onQueryChange={setFind}
                  onOpenResult={(_result: SearchResult) => {
                    setRightTab("xray");
                    setInspectorCollapsed(false);
                  }}
                />
              ) : null}
              {activeDrawer === "bugs" ? (
                <BugsDrawer
                  workspaceId={workspaceId}
                  scanEvent={bugsScanEvent}
                  onToast={(msg) => pushSystem(msg)}
                />
              ) : null}
              {activeDrawer === "receipts" ? (
                <ReceiptsDrawer workspaceId={workspaceId} />
              ) : null}
              {activeDrawer === "grammar" ? <GrammarHealthDrawer /> : null}
            </div>
          </aside>
        ) : null}

        <main
          style={{
            position: "relative",
            minWidth: 0,
            background: "var(--m42-bg-0)",
          }}
        >
          <SplitGraphContainer
            runState={runState}
            sourceLabel={sourceLang === "auto" ? "indexed" : sourceLang.toUpperCase()}
            targetLabel={targetLang.toUpperCase()}
            sourceSymbolCount={graphNodes.size || initialStats.files}
            targetSymbolCount={Math.floor(
              (progressPct / 100) * (graphNodes.size || initialStats.files)
            )}
            targetTotal={graphNodes.size || initialStats.files}
            renderSource={() => renderGraph("source")}
            renderTarget={() => renderGraph("target")}
            replicationPairs={[]}
          />

          {/* Breadcrumb pill, restyled to grayscale */}
          <nav
            className="pointer-events-none"
            aria-label="Breadcrumb"
            style={{
              position: "absolute",
              top: 12,
              left: "50%",
              transform: "translateX(-50%)",
              zIndex: 5,
            }}
          >
            <div
              data-testid="m42-breadcrumb"
              style={{
                pointerEvents: "auto",
                display: "inline-flex",
                alignItems: "center",
                gap: 8,
                padding: "6px 12px",
                background: "var(--m42-bg-1)",
                border: "0.5px solid var(--m42-border)",
                borderRadius: 999,
                fontFamily: "var(--omnix-font-mono)",
                fontSize: 11,
                color: "var(--m42-text-secondary)",
              }}
            >
              <button
                type="button"
                onClick={() => {
                  setSelectedNode(null);
                  void setScope("repo");
                }}
                style={{
                  background: "transparent",
                  border: 0,
                  color:
                    isReposScope && selectedNodeId == null
                      ? "var(--m42-text-primary)"
                      : "var(--m42-text-secondary)",
                  cursor: "pointer",
                  font: "inherit",
                }}
              >
                OMNIX
              </button>
              {crumbChain
                .filter((r) => r.id !== "repo")
                .map((r, i, arr) => (
                  <span key={r.id} style={{ display: "inline-flex", gap: 6, alignItems: "center" }}>
                    <span style={{ color: "var(--m42-text-tertiary)" }}>›</span>
                    {i < arr.length - 1 ? (
                      <button
                        type="button"
                        style={{
                          background: "transparent",
                          border: 0,
                          color: "var(--m42-text-secondary)",
                          cursor: "pointer",
                          font: "inherit",
                          maxWidth: "min(40vw, 18rem)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                        title={r.label}
                        onClick={() => {
                          void setScope(r.id);
                        }}
                      >
                        {r.label}
                      </button>
                    ) : (
                      <span
                        style={{
                          color: "var(--m42-text-primary)",
                          maxWidth: "min(40vw, 18rem)",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          whiteSpace: "nowrap",
                        }}
                        title={r.label}
                      >
                        {r.label}
                      </span>
                    )}
                  </span>
                ))}
            </div>
          </nav>

          {/* Find bar, kept floating at bottom-center of graph */}
          <div
            style={{
              position: "absolute",
              bottom: 16,
              left: "50%",
              transform: "translateX(-50%)",
              width: "min(100% - 2rem, 36rem)",
              zIndex: 6,
              pointerEvents: "none",
            }}
            role="search"
            aria-label="Find in project"
          >
            <div style={{ pointerEvents: "auto" }}>
              <FindBar
                value={find}
                onChange={setFind}
                onClear={find ? () => setFind("") : undefined}
              />
            </div>
          </div>

          {/* Source/target toggle (visible when split) for quick inspector switching */}
          {runState !== "idle" ? (
            <div
              style={{
                position: "absolute",
                top: 12,
                right: 16,
                display: "flex",
                gap: 4,
                zIndex: 6,
              }}
            >
              <button
                type="button"
                className={`m42-tab ${graphSide === "source" ? "is-active" : ""}`}
                style={{ flex: "0 0 auto", padding: "0 12px", height: 26 }}
                onClick={() => setGraphSide("source")}
              >
                SOURCE
              </button>
              <button
                type="button"
                className={`m42-tab ${graphSide === "target" ? "is-active" : ""}`}
                style={{ flex: "0 0 auto", padding: "0 12px", height: 26 }}
                onClick={() => setGraphSide("target")}
              >
                TARGET
              </button>
            </div>
          ) : null}
        </main>

        <Inspector
          activeTab={rightTab}
          onChangeTab={setRightTab}
          collapsed={inspectorCollapsed}
          onToggleCollapsed={() => setInspectorCollapsed((s) => !s)}
        >
          {inspectorContent}
        </Inspector>
      </div>

      <BottomBar
        runState={runState}
        sourceLang={sourceLang}
        onSourceLangChange={setSourceLang}
        targetLang={targetLang}
        onTargetLangChange={setTargetLang}
        onStart={onStart}
        onPause={() => {
          setRunState("idle");
          pushSystem("Run paused (stub).");
        }}
        onAbort={() => {
          setRunState("idle");
          setProgressPct(0);
          setEtaSec(null);
          setCurrentSymbol(null);
          pushSystem("Run aborted.");
        }}
        onSeeDecision={() => setDecisionOpen(true)}
        onVerifyReceipt={() => {
          pushSystem(`Verified receipt ${doneReceiptHash ?? "—"}`);
        }}
        onDownloadZip={() => pushSystem("Bundle .zip stub — wire to /api/rebuild/download.")}
        onDownloadPdf={() => pushSystem("PDF report stub — wire to /api/rebuild/report.")}
        onStartAnother={() => {
          setRunState("idle");
          setProgressPct(0);
          setEtaSec(null);
          setCurrentSymbol(null);
          setDoneSummary(null);
          setDoneReceiptHash(null);
          setGraphSide("source");
        }}
        progressPct={progressPct}
        etaSeconds={etaSec}
        currentSymbol={currentSymbol}
        doneSummary={doneSummary}
        doneReceiptHash={doneReceiptHash}
      />

      <DecisionModal
        open={decisionOpen}
        payload={decisionPayload ?? defaultDecision(currentSymbol ?? "unknown_symbol")}
        onContinue={(selection) => {
          setDecisionOpen(false);
          setRunState("running");
          pushAgent(
            selection.optionId === "__custom__"
              ? `Custom decision: ${selection.custom}. Resuming.`
              : `Applied "${selection.optionId}". Resuming.`
          );
        }}
        onSkip={() => {
          setDecisionOpen(false);
          setRunState("idle");
          pushSystem("Decision skipped — run paused.");
        }}
        onClose={() => setDecisionOpen(false)}
      />

      {cutoverUnit && (
        <CutoverModal unit={cutoverUnit} onClose={() => setCutoverUnit(null)} />
      )}

      <SlideSettingsDrawer
        open={settingsOpen}
        onClose={() => setSettingsOpen(false)}
        sections={settingsSections}
        active={settingsSection}
        onActiveChange={setSettingsSection}
      />
    </div>
  );
}
