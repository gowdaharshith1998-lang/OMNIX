import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { GraphCanvas, type GraphCanvasHandle } from "./Graph/GraphCanvas";
import { ConstellationBoundary } from "./ConstellationBoundary";
import {
  createFile,
  listFiles,
  type BugFinding,
  type BugScanSummary,
  type BugsScanEvent,
  type FileEntry,
  type SearchResult,
} from "@/lib/api";
import { isT1Mode } from "@/lib/t1Mode";
import { StudioWebSocket } from "@/lib/ws";
import { useStudioKeybindings } from "@/lib/keybindings";
import { BottomToolbar } from "./BottomToolbar";
import { CodeTab, type CodeTabHandle, type CodeTarget } from "./CodeTab";
import { BugsDrawer } from "./drawers/BugsDrawer";
import { FilesDrawer } from "./drawers/FilesDrawer";
import { ReceiptsDrawer } from "./drawers/ReceiptsDrawer";
import { SearchDrawer } from "./drawers/SearchDrawer";
import { SettingsDrawer } from "./drawers/SettingsDrawer";
import { FindBar } from "./FindBar";
import { HistoryTab } from "./HistoryTab";
import { LeftRail, type LeftRailDrawer } from "./LeftRail";
import { NewFileModal } from "./NewFileModal";
import { RightPanel, type RightPanelTab, type RightPanelTabId } from "./RightPanel";
import { StatsPanel } from "./StatsPanel";
import { XRayTab } from "./XRayTab";
import { BootstrapOverlay } from "./BootstrapOverlay";
import { EmptyScopeState } from "./EmptyScopeState";
import {
  ReconnectIndicator,
  type ReconnectIndicatorMode,
} from "./ReconnectIndicator";
import type { GraphEdge, GraphNode } from "@/types/drilldown";
import {
  applyNodeModified,
  recordEdgeFromGraphPayload,
  recordFromGraphPayload,
} from "@/lib/graphNode";
import {
  loadShellLayout,
  saveShellLayout,
  type ShellLayoutState,
} from "@/lib/persisted_widths";
import type {
  ScopeNavigationSpec,
  ScopeVisualEmptyDetail,
  ViewerScopePayload,
} from "./Graph/StudioGraph";
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
import { installGlobalErrorTrap } from "@/lib/globalErrorTrap";

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

function isDebugOn() {
  if (import.meta.env.DEV) return true;
  if (import.meta.env.VITE_OMNIX_STUDIO_DEBUG === "1") return true;
  if (new URLSearchParams(window.location.search).get("debug") === "1") {
    return true;
  }
  return false;
}

function projectLabel(p: string) {
  const s = p.replace(/\\/g, "/");
  const parts = s.split("/").filter(Boolean);
  return parts.length > 0 ? (parts[parts.length - 1] as string) : s;
}

function isBugsScanEvent(msg: Record<string, unknown>): msg is BugsScanEvent {
  return (
    msg.type === "bugs_scan_started" ||
    msg.type === "bugs_scan_heartbeat" ||
    msg.type === "bugs_scan_complete" ||
    msg.type === "bugs_scan_error"
  );
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

function normalizeScopeFsPath(p: string | undefined): string {
  return (p ?? "").replace(/\\/g, "/");
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

export function Workspace({
  workspaceId,
  projectPath,
  initialStats,
  onBack,
}: Props) {
  const [find, setFind] = useState("");
  const [shellLayout, setShellLayout] = useState<ShellLayoutState>(() =>
    loadShellLayout(projectPath)
  );
  const bootstrapTotals = useMemo(
    () => ({
      files: initialStats.files,
      functions: initialStats.functions,
      classes: initialStats.classes,
      edges: initialStats.edges,
      dark_matter: 0,
      entangled: 0,
    }),
    [
      initialStats.classes,
      initialStats.edges,
      initialStats.files,
      initialStats.functions,
    ]
  );
  const [wsState, setWsState] = useState<WsState>("idle");
  const [, setFiles] = useState<FileEntry[]>([]);
  const [newFile, setNewFile] = useState(false);
  const [activeDrawer, setActiveDrawer] = useState<LeftRailDrawer | null>(
    shellLayout.leftDrawer.openTab
  );
  const [lastDrawerTab, setLastDrawerTab] = useState<LeftRailDrawer>(
    shellLayout.leftDrawer.openTab ?? "files"
  );
  const [rightTab, setRightTab] = useState<RightPanelTabId>("xray");
  const [toast, setToast] = useState<string | null>(null);
  const [bugsScanEvent, setBugsScanEvent] = useState<BugsScanEvent | null>(null);
  const [bugsScanFindings, setBugsScanFindings] = useState<BugFinding[]>([]);
  const [bugsScanSummary, setBugsScanSummary] = useState<BugScanSummary | null>(
    null
  );
  const [graphHint] = useState<string[]>([]);
  const [codeTarget, setCodeTarget] = useState<CodeTarget | null>(null);
  const [graphCanGoBack, setGraphCanGoBack] = useState(false);
  const [graphNodes, setGraphNodes] = useState<Map<string, GraphNode>>(
    () => new Map()
  );
  const [graphEdges, setGraphEdges] = useState<GraphEdge[]>([]);
  const [scopeRecords, setScopeRecords] =
    useState<ScopeRecord[]>(CANONICAL_SCOPES);
  const [emptyScopeOverlay, setEmptyScopeOverlay] =
    useState<ScopeVisualEmptyDetail | null>(null);
  const [viewerScopePathEcho, setViewerScopePathEcho] = useState("");

  const { currentScope, selectedNodeId } = useScope();
  const [constellationMountEpoch, setConstellationMountEpoch] = useState(0);
  const scopeMaps = useMemo(
    () => scopeRecordsToMaps(scopeRecords),
    [scopeRecords]
  );
  const scopeById = scopeMaps.byId;
  const pathToScopeId = scopeMaps.pathToId;

  const pathToScopeIdRef = useRef(pathToScopeId);
  pathToScopeIdRef.current = pathToScopeId;
  const scopeByIdRef = useRef(scopeById);
  scopeByIdRef.current = scopeById;

  const nodesList = useMemo(
    () => Array.from(graphNodes.values()),
    [graphNodes]
  );

  const displayStats = useMemo(() => {
    const rec = scopeById.get(currentScope);
    const prefix = rec?.pathPrefix ?? null;
    if (currentScope === "repo" && graphNodes.size === 0) {
      return bootstrapTotals;
    }
    const m = computeScopedStats(nodesList, graphEdges, prefix);
    return {
      files: m.files,
      functions: m.functions,
      classes: m.classes,
      edges: m.edges,
      dark_matter: m.dark_matter,
      entangled: m.entangled,
    };
  }, [
    bootstrapTotals,
    currentScope,
    graphEdges,
    graphNodes.size,
    nodesList,
    scopeById,
  ]);

  const navigationSpec = useMemo(
    () => navigationSpecForScopeRecord(currentScope, scopeById),
    [currentScope, scopeById]
  );

  const graphNodesRef = useRef(graphNodes);
  const lastViewerScopePayloadRef = useRef<ViewerScopePayload>({ kind: "repo" });
  const constellationScopePathRef = useRef<string>("");
  const graphRef = useRef<GraphCanvasHandle | null>(null);
  const codeRef = useRef<CodeTabHandle | null>(null);
  const codePathRef = useRef<string | null>(null);
  /** After first successful WS open; used to distinguish initial connect vs reconnect (slice 6c). */
  const hasConnectedBeforeRef = useRef(false);
  /** First live bootstrap_complete only (never reset — slice 6d). */
  const hasBootstrappedRef = useRef(false);
  const bootstrapHideTimerRef = useRef<ReturnType<typeof setTimeout> | null>(
    null
  );
  const [bootstrapPhase, setBootstrapPhase] = useState<
    "pending" | "shown" | "hiding" | "hidden"
  >("pending");
  /** null until first `bootstrap_start` for this session (slice 18a-lite). */
  const [bootstrapFileHint, setBootstrapFileHint] = useState<{
    source: "ws";
    total: number;
  } | null>(null);
  const [reconnectedPhase, setReconnectedPhase] = useState<
    "hidden" | "shown" | "fade"
  >("hidden");
  useEffect(() => {
    graphNodesRef.current = graphNodes;
  }, [graphNodes]);

  useEffect(() => {
    codePathRef.current = codeTarget?.path ?? null;
  }, [codeTarget?.path]);

  useEffect(() => {
    document.documentElement.style.setProperty(
      "--left-drawer-width",
      `${shellLayout.leftDrawer.width}px`
    );
    document.documentElement.style.setProperty(
      "--right-panel-width",
      `${shellLayout.rightPanel.width}px`
    );
  }, [shellLayout.leftDrawer.width, shellLayout.rightPanel.width]);

  const persistShellLayout = useCallback(
    (next: ShellLayoutState) => {
      setShellLayout(next);
      saveShellLayout(projectPath, next);
    },
    [projectPath]
  );

  const setPersistentDrawer = useCallback(
    (drawer: LeftRailDrawer | null) => {
      if (drawer) setLastDrawerTab(drawer);
      setActiveDrawer(drawer);
      persistShellLayout({
        ...shellLayout,
        leftDrawer: { ...shellLayout.leftDrawer, openTab: drawer },
      });
    },
    [persistShellLayout, shellLayout]
  );

  const setRightPanelCollapsed = useCallback(
    (collapsed: boolean) => {
      persistShellLayout({
        ...shellLayout,
        rightPanel: { ...shellLayout.rightPanel, collapsed },
      });
    },
    [persistShellLayout, shellLayout]
  );

  const expandRightPanel = useCallback(() => {
    if (shellLayout.rightPanel.collapsed) setRightPanelCollapsed(false);
  }, [setRightPanelCollapsed, shellLayout.rightPanel.collapsed]);

  const showToastStable = useCallback(
    (message: string, durationMs?: number) => {
      setToast(message);
      setTimeout(
        () => {
          setToast((t) => (t === message ? null : t));
        },
        durationMs ?? (message === "saved" ? 1000 : 2200)
      );
    },
    []
  );

  useEffect(() => {
    configureStudioScopeHandlers({
      onInvalidScope: (id) => {
        showToastStable(`Unknown scope: ${id}`, 2600);
      },
    });
  }, [showToastStable]);

  useEffect(() => {
    const uninstall = installGlobalErrorTrap({
      onToast: (message, durationMs) => showToastStable(message, durationMs),
    });
    return uninstall;
  }, [showToastStable]);

  useEffect(() => {
    const allow =
      import.meta.env.DEV || import.meta.env.VITE_OMNIX_STUDIO_DEBUG === "1";
    if (!allow) return;
    const w = window as unknown as {
      studioGraph?: { simulateRenderError?: () => void };
    };
    w.studioGraph = {
      simulateRenderError: () => graphRef.current?.simulateRenderError?.(),
    };
    return () => {
      delete w.studioGraph;
    };
  }, []);

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

  const onViewerScope = useCallback(
    (payload: ViewerScopePayload) => {
      lastViewerScopePayloadRef.current = payload;
      constellationScopePathRef.current =
        payload.kind === "repo" ? "" : normalizeScopeFsPath(payload.path);
      setViewerScopePathEcho(constellationScopePathRef.current);
      const id = scopeIdFromViewerPayload(payload, pathToScopeIdRef.current);
      syncScopeFromViewer(id, {
        pathPrefixForScope: (sid) => scopeByIdRef.current.get(sid)?.pathPrefix ?? null,
        selectedFilePath: () => {
          const sid = getStudioScopeSnapshot().selectedNodeId;
          return sid ? graphNodesRef.current.get(sid)?.file_path ?? null : null;
        },
      });
      queueMicrotask(() => {
        const expected = scopeIdFromViewerPayload(
          lastViewerScopePayloadRef.current,
          pathToScopeIdRef.current
        );
        const snap = getStudioScopeSnapshot();
        if (snap.selectedNodeId != null) return;
        if (snap.currentScope !== expected) {
          showToastStable("Scope resynchronized", 2000);
          syncScopeFromViewer(expected, {
            pathPrefixForScope: (sid) =>
              scopeByIdRef.current.get(sid)?.pathPrefix ?? null,
            selectedFilePath: () => {
              const sid = getStudioScopeSnapshot().selectedNodeId;
              return sid ? graphNodesRef.current.get(sid)?.file_path ?? null : null;
            },
          });
        }
      });
    },
    [showToastStable]
  );

  const onScopeVisualEmpty = useCallback((detail: ScopeVisualEmptyDetail | null) => {
    setEmptyScopeOverlay(detail);
  }, []);

  const refreshFiles = useCallback(async () => {
    try {
      setFiles(await listFiles(workspaceId, ""));
    } catch {
      setFiles([]);
    }
  }, [workspaceId]);

  useEffect(() => {
    void refreshFiles();
  }, [refreshFiles]);

  const openCodeFile = useCallback((p: string) => {
    setCodeTarget({ path: p });
    setRightTab("code");
  }, []);

  const selectXRayNode = useCallback((node: GraphNode | null) => {
    setSelectedNode(node?.id ?? null);
    setRightTab("xray");
    expandRightPanel();
  }, [expandRightPanel]);

  const findNodeForPath = useCallback((p: string) => {
    const normalized = p.replace(/\\/g, "/");
    const nodes = Array.from(graphNodesRef.current.values());
    return (
      nodes.find((node) => node.id === normalized) ??
      nodes.find((node) => node.file_path === normalized) ??
      nodes.find((node) => node.file_path && normalized.startsWith(node.file_path)) ??
      null
    );
  }, []);

  const openXRayFileOrDir = useCallback(
    (p: string) => {
      const node = findNodeForPath(p);
      if (node?.file_path) setCodeTarget({ path: node.file_path });
      else setCodeTarget({ path: p });
      const dirLike =
        node != null &&
        (node.type === "directory" ||
          node.type === "module" ||
          node.type === "folder");
      if (dirLike) {
        setSelectedNode(null);
        setRightTab("xray");
        expandRightPanel();
        return;
      }
      selectXRayNode(node);
    },
    [expandRightPanel, findNodeForPath, selectXRayNode]
  );

  const openXRayNode = useCallback(
    (nodeId: string) => {
      const n = graphNodesRef.current.get(nodeId);
      if (!n || !n.file_path) {
        showToastStable("node not found in graph index", 2600);
        return;
      }
      setCodeTarget({
        nodeId: n.id,
        path: n.file_path,
        lineStart: n.line_start,
        lineEnd: n.line_end,
        name: n.name,
      });
      selectXRayNode(n);
    },
    [selectXRayNode, showToastStable]
  );

  const handleGraphBack = useCallback(() => {
    if (!graphRef.current?.canGoBack()) return false;
    graphRef.current.goBack();
    setGraphCanGoBack(graphRef.current.canGoBack());
    return true;
  }, []);

  const findNodeForSearchResult = useCallback((result: SearchResult) => {
    const normalizedPath = result.path.replace(/\\/g, "/");
    const nodes = Array.from(graphNodesRef.current.values());
    return (
      nodes.find(
        (node) =>
          node.file_path === normalizedPath &&
          node.line_start === result.line &&
          node.name === result.name
      ) ??
      nodes.find(
        (node) => node.file_path === normalizedPath && node.line_start === result.line
      ) ??
      nodes.find((node) => node.file_path === normalizedPath && node.name === result.name) ??
      findNodeForPath(normalizedPath)
    );
  }, [findNodeForPath]);

  const onT1GraphNodes = useCallback((list: GraphNode[]) => {
    setGraphNodes((prev) => {
      const next = new Map(prev);
      for (const n of list) {
        next.set(n.id, n);
      }
      return next;
    });
  }, []);

  const onT1GraphEdges = useCallback((list: GraphEdge[]) => {
    setGraphEdges(list);
  }, []);

  const [codeExternalEpoch, setCodeExternalEpoch] = useState(0);

  const noteCodeFileTouched = useCallback((path: string | null) => {
    const openPath = codePathRef.current;
    if (path && openPath && path === openPath) {
      setCodeExternalEpoch((epoch) => epoch + 1);
    }
  }, []);

  const ingestWorkspaceMessage = useCallback(
    (msg: Record<string, unknown>) => {
      const kind = typeof msg.type === "string" ? msg.type : "";
      if (kind === "node_added" && msg.node && typeof msg.node === "object") {
        const rec = recordFromGraphPayload(msg.node as Record<string, unknown>);
        if (rec) {
          setGraphNodes((prev) => {
            const next = new Map(prev);
            next.set(rec.id, rec);
            return next;
          });
          noteCodeFileTouched(rec.file_path);
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
        }
        return;
      }
      if (kind === "edge_removed" && msg.edge_id != null) {
        const id = String(msg.edge_id);
        setGraphEdges((prev) => prev.filter((edge) => String(edge.id) !== id));
        return;
      }
      if (kind === "node_modified" && typeof msg.node_id === "string") {
        const prevNode = graphNodesRef.current.get(msg.node_id);
        if (prevNode) {
          noteCodeFileTouched(prevNode.file_path);
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
          noteCodeFileTouched(nextNode.file_path);
        }
        return;
      }
      if (kind === "node_removed" && typeof msg.node_id === "string") {
        const prevNode = graphNodesRef.current.get(msg.node_id);
        noteCodeFileTouched(prevNode?.file_path ?? null);
        setGraphNodes((prev) => {
          const next = new Map(prev);
          next.delete(msg.node_id as string);
          return next;
        });
        return;
      }
      if (
        (kind === "file_added" || kind === "file_removed") &&
        typeof msg.path === "string"
      ) {
        noteCodeFileTouched(msg.path);
      }
    },
    [noteCodeFileTouched]
  );

  useEffect(() => {
    if (isT1Mode()) return;

    const c = new StudioWebSocket(
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
        if (m.type === "bootstrap_start" && !hasBootstrappedRef.current) {
          const tf = m.total_files;
          setBootstrapFileHint({
            source: "ws",
            total: typeof tf === "number" ? tf : 0,
          });
        }
        if (m.type === "bootstrap_complete" && !hasBootstrappedRef.current) {
          hasBootstrappedRef.current = true;
          setBootstrapPhase("hiding");
          if (bootstrapHideTimerRef.current != null) {
            clearTimeout(bootstrapHideTimerRef.current);
          }
          bootstrapHideTimerRef.current = setTimeout(() => {
            bootstrapHideTimerRef.current = null;
            setBootstrapPhase("hidden");
          }, 300);
        }
        graphRef.current?.ingestMessage(msg);
        ingestWorkspaceMessage(m);
      },
      (s) => {
        if (s === "connecting") setWsState("connecting");
        if (s === "open") {
          const wasReconnect = hasConnectedBeforeRef.current;
          // eslint-disable-next-line no-console
          console.log("[t2-slice1] ws open");
          setWsState("open");
          hasConnectedBeforeRef.current = true;
          if (wasReconnect) setReconnectedPhase("shown");
        }
        if (s === "closed") setWsState("closed");
      },
      (code) => {
        // eslint-disable-next-line no-console
        console.log("[t2-slice1] ws close", code);
      }
    );
    c.connect();
    return () => {
      if (bootstrapHideTimerRef.current != null) {
        clearTimeout(bootstrapHideTimerRef.current);
        bootstrapHideTimerRef.current = null;
      }
      c.close();
    };
  }, [ingestWorkspaceMessage, workspaceId]);

  useEffect(() => {
    if (isT1Mode()) setBootstrapPhase("hidden");
  }, []);

  const isReconnecting =
    (wsState === "connecting" || wsState === "closed") &&
    hasConnectedBeforeRef.current;

  useEffect(() => {
    if (isReconnecting) setReconnectedPhase("hidden");
  }, [isReconnecting]);

  useEffect(() => {
    if (reconnectedPhase !== "shown") return;
    const t1 = setTimeout(() => setReconnectedPhase("fade"), 800);
    const t2 = setTimeout(() => setReconnectedPhase("hidden"), 1000);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
    };
  }, [reconnectedPhase]);

  let reconnectIndicatorMode: ReconnectIndicatorMode = "hidden";
  if (isReconnecting) reconnectIndicatorMode = "reconnecting";
  else if (reconnectedPhase === "shown") reconnectIndicatorMode = "reconnected";
  else if (reconnectedPhase === "fade") reconnectIndicatorMode = "reconnected-fade";

  const loadingGate =
    (wsState === "connecting" || wsState === "open") &&
    !hasBootstrappedRef.current &&
    !isReconnecting;

  const bootstrapOverlayFileCount = useMemo(() => {
    if (bootstrapFileHint?.source === "ws") {
      return bootstrapFileHint.total > 0 ? bootstrapFileHint.total : null;
    }
    return initialStats.files > 0 ? initialStats.files : null;
  }, [bootstrapFileHint, initialStats.files]);

  useEffect(() => {
    if (isT1Mode()) return;
    if (bootstrapPhase === "pending" && loadingGate) {
      setBootstrapPhase("shown");
    }
  }, [bootstrapPhase, loadingGate]);

  const bootstrapIndicatorPhase =
    isT1Mode() || bootstrapPhase === "hidden"
      ? "hidden"
      : bootstrapPhase === "hiding"
        ? "hiding"
        : loadingGate
          ? "shown"
          : "hidden";

  const slice18aOverlayShownProbeRef = useRef(false);
  useEffect(() => {
    if (isT1Mode()) return;
    if (
      bootstrapIndicatorPhase === "shown" &&
      !slice18aOverlayShownProbeRef.current
    ) {
      slice18aOverlayShownProbeRef.current = true;
    }
  }, [bootstrapIndicatorPhase]);

  useEffect(() => {
    if (!codeTarget?.nodeId) return;
    const id = codeTarget.nodeId;
    const inMap = graphNodes.get(id);
    if (!inMap) return;
    if (
      inMap.line_start !== codeTarget.lineStart ||
      inMap.line_end !== codeTarget.lineEnd
    ) {
      setCodeTarget((prev) => {
        if (!prev || prev.nodeId !== id) return prev;
        return {
          ...prev,
          lineStart: inMap.line_start,
          lineEnd: inMap.line_end,
        };
      });
    }
  }, [codeTarget, graphNodes]);

  useEffect(() => {
    if (!isDebugOn()) return;
    (window as unknown as { __omnix_select_node?: (id: string) => void })
      .__omnix_select_node = (nodeId: string) => {
      openXRayNode(nodeId);
    };
    // eslint-disable-next-line no-console
    console.info("debug: window.__omnix_select_node(nodeId) ready");
    return () => {
      const w = window as unknown as { __omnix_select_node?: unknown };
      if (w.__omnix_select_node) delete w.__omnix_select_node;
    };
  }, [openXRayNode]);

  const onDrillSaveShell = useCallback(() => {
    setToast("Code tab save lands next");
    setTimeout(() => setToast(null), 2200);
  }, []);

  const pName = projectLabel(projectPath);
  const searchFallbackNodes = useMemo(() => Array.from(graphNodes.values()), [graphNodes]);

  const drawerContent: Record<LeftRailDrawer, ReactNode> = {
    files: <FilesDrawer workspaceId={workspaceId} onOpenFile={openCodeFile} />,
    search: (
      <SearchDrawer
        workspaceId={workspaceId}
        query={find}
        fallbackNodes={searchFallbackNodes}
        onQueryChange={setFind}
        onOpenResult={(result) => {
          const node = findNodeForSearchResult(result);
          setCodeTarget({
            nodeId: node?.id,
            path: result.path,
            lineStart: result.line || undefined,
            lineEnd: (node?.line_end ?? result.line) || undefined,
            name: result.name || node?.name,
          });
          if (node) selectXRayNode(node);
          else setRightTab("code");
        }}
      />
    ),
    bugs: (
      <BugsDrawer
        workspaceId={workspaceId}
        scanEvent={bugsScanEvent}
        onToast={showToastStable}
      />
    ),
    receipts: <ReceiptsDrawer workspaceId={workspaceId} />,
    settings: <SettingsDrawer projectPath={projectPath} />,
  };

  const rightTabs: RightPanelTab[] = [
    {
      id: "xray",
      label: "X-Ray",
      content: (
        <XRayTab
          workspaceId={workspaceId}
          scopeAtomId={currentScope}
          graphNodes={graphNodes}
          graphEdges={graphEdges}
          stats={displayStats}
          scopeById={scopeById}
          projectPath={projectPath}
          bugsScanFindings={bugsScanFindings}
          bugsScanSummary={bugsScanSummary}
          onSuggestedAction={() =>
            showToastStable("action wiring lands in slice 15", 15000)
          }
        />
      ),
    },
    {
      id: "code",
      label: "Code",
      content: (
        <CodeTab
          ref={codeRef}
          workspaceId={workspaceId}
          target={codeTarget}
          externalFileEpoch={codeExternalEpoch}
          onToast={showToastStable}
        />
      ),
    },
    {
      id: "history",
      label: "History",
      content: <HistoryTab workspaceId={workspaceId} />,
    },
  ];

  const activateScopeFromBreadcrumb = useCallback((id: string) => {
    if (id === "repo") setSelectedNode(null);
    void setScope(id);
  }, []);

  const handleEmptyScopeBack = useCallback(() => {
    setEmptyScopeOverlay(null);
    if (graphRef.current?.canGoBack()) {
      graphRef.current.goBack();
      return;
    }
    void setScope("repo");
    graphRef.current?.applyScopeNavigation({ kind: "repo" });
  }, []);

  const crumbChain = ancestryChain(currentScope, scopeById);

  useStudioKeybindings({
    drillOpen: codeTarget != null,
    onEscape: () => {
      if (activeDrawer) {
        setPersistentDrawer(null);
        return true;
      }
      if (newFile) {
        setNewFile(false);
        return true;
      }
      if (handleGraphBack()) return true;
      return false;
    },
    onTogglePicker: () =>
      setPersistentDrawer(activeDrawer === "search" ? null : "search"),
    onToggleLeftDrawer: () =>
      setPersistentDrawer(activeDrawer ? null : lastDrawerTab),
    onToggleRightPanel: () =>
      setRightPanelCollapsed(!shellLayout.rightPanel.collapsed),
    onNewFile: () => setNewFile(true),
    onCmdSWhenNoDrill: onDrillSaveShell,
    onSaveDrill: () => codeRef.current?.save(),
  });

  return (
    <div className="omnix-hex-bg relative h-full min-h-0 w-full font-sans text-omnix-text-primary">
      <LeftRail
        active={activeDrawer}
        drawerWidth={shellLayout.leftDrawer.width}
        onSelect={setPersistentDrawer}
        onClose={() => setPersistentDrawer(null)}
        onResizeEnd={(width) =>
          persistShellLayout({
            ...shellLayout,
            leftDrawer: { ...shellLayout.leftDrawer, width },
          })
        }
      >
        {activeDrawer ? drawerContent[activeDrawer] : null}
      </LeftRail>

      <nav
        className="pointer-events-none fixed left-1/2 top-5 z-[30] w-[min(100%-2rem,720px)] -translate-x-1/2 px-4 text-center"
        aria-label="Breadcrumb"
      >
        <div
          className="omnix-glass pointer-events-auto mx-auto flex w-max max-w-full flex-wrap items-center justify-center gap-1.5 rounded-full border border-omnix-accent-indigo/25 px-4 py-2 font-mono text-xs"
          data-studio-breadcrumb="1"
          data-testid="breadcrumb"
        >
          {graphCanGoBack ? (
            <button
              type="button"
              aria-label="Back in graph"
              onClick={handleGraphBack}
              className="text-omnix-text-primary transition hover:rounded-md hover:bg-[rgba(99,102,241,0.15)]"
            >
              &lt; Back
            </button>
          ) : null}
          <button
            type="button"
            disabled={currentScope === "repo" && selectedNodeId == null}
            onClick={() => activateScopeFromBreadcrumb("repo")}
            className={
              currentScope === "repo" && selectedNodeId == null
                ? "cursor-default text-omnix-text-primary"
                : "text-omnix-text-muted transition hover:rounded-md hover:bg-[rgba(99,102,241,0.15)] hover:text-omnix-text-primary"
            }
          >
            OMNIX
          </button>
          {crumbChain
            .filter((r) => r.id !== "repo")
            .map((r, i, arr) => (
              <span key={r.id} className="flex items-center gap-1.5">
                <span className="text-omnix-text-sep select-none">›</span>
                {i < arr.length - 1 ? (
                  <button
                    type="button"
                    className="max-w-[min(40vw,18rem)] truncate text-omnix-text-muted transition hover:rounded-md hover:bg-[rgba(99,102,241,0.15)] hover:text-omnix-text-primary"
                    title={r.label}
                    onClick={() => activateScopeFromBreadcrumb(r.id)}
                  >
                    {r.label}
                  </button>
                ) : (
                  <span
                    className="max-w-[min(40vw,18rem)] truncate text-omnix-text-primary"
                    title={r.label}
                  >
                    {r.label}
                  </span>
                )}
              </span>
            ))}
          <span className="text-omnix-text-sep select-none">›</span>
          <span
            className="max-w-[min(50vw,24rem)] truncate text-omnix-text-muted"
            title={projectPath}
          >
            {pName}
          </span>
          <button
            type="button"
            className="ml-1 text-[10px] uppercase tracking-wide text-omnix-text-dim hover:text-omnix-text-primary"
            onClick={onBack}
          >
            Exit
          </button>
        </div>
      </nav>

      <ReconnectIndicator mode={reconnectIndicatorMode} />
      <BootstrapOverlay
        phase={bootstrapIndicatorPhase}
        fileCount={bootstrapOverlayFileCount}
      />

      <div className="flex h-full min-h-0 w-full min-w-0 flex-col">
        <div className="relative min-h-0 w-full min-w-0 flex-1">
          <main className="flex h-full min-h-0 w-full min-w-0 flex-col p-3 pt-14">
            <div className="mb-2 text-[10px] font-mono font-medium uppercase tracking-[0.15em] text-omnix-text-dim">
              graph
            </div>
            <div
              className="relative min-h-0 min-w-0 flex-1 overflow-hidden rounded-lg border border-omnix-accent-indigo/20 bg-[rgba(2,6,21,0.5)]"
              data-omnix-constellation="1"
              data-studio-viewer-scope-path={viewerScopePathEcho}
            >
              <ConstellationBoundary
                onRetry={() => setConstellationMountEpoch((n) => n + 1)}
              >
                <GraphCanvas
                  key={constellationMountEpoch}
                  ref={graphRef}
                  drillDownNodeId={codeTarget?.nodeId ?? null}
                  navigationSpec={navigationSpec}
                  onFunctionNodeClick={openXRayNode}
                  onT1GraphNodes={onT1GraphNodes}
                  onT1GraphEdges={onT1GraphEdges}
                  onFileOrDirClick={openXRayFileOrDir}
                  onDeselect={() => undefined}
                  onNavigationStateChange={setGraphCanGoBack}
                  onViewerScope={onViewerScope}
                  onScopeVisualEmpty={onScopeVisualEmpty}
                />
              </ConstellationBoundary>
              {emptyScopeOverlay ? (
                <EmptyScopeState
                  scopePath={emptyScopeOverlay.scopePath}
                  onBack={handleEmptyScopeBack}
                />
              ) : null}
              <div
                data-omnix-stats-card="1"
                className="pointer-events-auto absolute right-4 top-4 z-20 font-mono"
                aria-label="Graph stats"
              >
                <StatsPanel stats={displayStats} variant="constellation" />
              </div>
              <div
                data-omnix-find-slot="1"
                className="pointer-events-none absolute bottom-[50px] left-1/2 z-30 w-[min(100%-2rem,42rem)] max-w-2xl -translate-x-1/2 px-3"
                role="search"
                aria-label="Find in project"
              >
                <div className="pointer-events-auto w-full">
                  <FindBar
                    value={find}
                    onChange={setFind}
                    onClear={find ? () => setFind("") : undefined}
                  />
                </div>
              </div>
              {graphHint.length > 0 && (
                <div className="pointer-events-none absolute bottom-2 left-2 z-10 max-w-[min(100%,20rem)] rounded border border-omnix-accent-indigo/20 bg-omnix-bg/80 px-2 py-1 font-mono text-[9px] text-omnix-text-dim/90">
                  recent: {graphHint.join(" · ")}
                </div>
              )}
              {isDebugOn() && (
                <p className="pointer-events-none absolute left-2 top-2 z-10 font-mono text-[9px] text-omnix-text-dim/70">
                  ws: {wsState}
                </p>
              )}
            </div>
          </main>
        </div>
      </div>

      <RightPanel
        tabs={rightTabs}
        activeTab={rightTab}
        width={shellLayout.rightPanel.width}
        collapsed={shellLayout.rightPanel.collapsed}
        onSelectTab={setRightTab}
        onNewAgentTab={() => showToastStable("Agent tabs land in slice 15", 1800)}
        onResizeEnd={(width) =>
          persistShellLayout({
            ...shellLayout,
            rightPanel: { ...shellLayout.rightPanel, width },
          })
        }
        onToggleCollapsed={() =>
          setRightPanelCollapsed(!shellLayout.rightPanel.collapsed)
        }
      />

      <div
        className="pointer-events-none fixed bottom-5 left-0 right-0 z-40 flex justify-center px-3 pl-12"
        aria-label="OMNIX toolbar"
      >
        <div className="pointer-events-auto w-full max-w-5xl">
          <BottomToolbar
            onDarkMatter={() => {
              showToastStable("Dark matter — with graph (Day 11+)", 2000);
            }}
            onTimeline={() => {
              showToastStable("Timeline — with graph (Day 11+)", 2000);
            }}
            onExportJson={() => {
              showToastStable("Export graph JSON — with graph (Day 11+)", 2000);
            }}
          />
        </div>
      </div>

      <NewFileModal
        open={newFile}
        onClose={() => setNewFile(false)}
        onCreate={async (rel, content) => {
          await createFile(workspaceId, rel, content);
          await refreshFiles();
        }}
      />

      {toast && (
        <div
          className="omnix-glass pointer-events-none fixed bottom-24 left-1/2 z-[60] -translate-x-1/2 rounded-md border border-omnix-accent-indigo/25 px-3 py-1.5 text-xs text-omnix-text-primary shadow-omnix-glass"
        >
          {toast}
        </div>
      )}
    </div>
  );
}
