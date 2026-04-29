import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { GraphCanvas, type GraphCanvasHandle } from "./Graph/GraphCanvas";
import { createFile, listFiles, type FileEntry } from "@/lib/api";
import { isT1Mode } from "@/lib/t1Mode";
import { StudioWebSocket } from "@/lib/ws";
import { useStudioKeybindings } from "@/lib/keybindings";
import { BottomToolbar } from "./BottomToolbar";
import { CodeTab, type CodeTabHandle, type CodeTarget } from "./CodeTab";
import { FilesDrawer } from "./drawers/FilesDrawer";
import { ReceiptsDrawer } from "./drawers/ReceiptsDrawer";
import { FindBar } from "./FindBar";
import { HistoryTab } from "./HistoryTab";
import { LeftRail, type LeftRailDrawer } from "./LeftRail";
import { NewFileModal } from "./NewFileModal";
import { RightPanel, type RightPanelTab, type RightPanelTabId } from "./RightPanel";
import { StatsPanel } from "./StatsPanel";
import { BootstrapIndicator } from "./BootstrapIndicator";
import {
  ReconnectIndicator,
  type ReconnectIndicatorMode,
} from "./ReconnectIndicator";
import type { GraphNode } from "@/types/drilldown";
import { applyNodeModified, recordFromGraphPayload } from "@/lib/graphNode";

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

function DrawerPlaceholder({ label }: { label: string }) {
  return (
    <div className="p-4 text-sm text-omnix-text-dim">
      {label} drawer content lands in this slice.
    </div>
  );
}

export function Workspace({
  workspaceId,
  projectPath,
  initialStats,
  onBack,
}: Props) {
  const [find, setFind] = useState("");
  const [stats] = useState({
    files: initialStats.files,
    functions: initialStats.functions,
    classes: initialStats.classes,
    edges: initialStats.edges,
    dark_matter: 0,
    entangled: 0,
  });
  const [wsState, setWsState] = useState<WsState>("idle");
  const [, setFiles] = useState<FileEntry[]>([]);
  const [newFile, setNewFile] = useState(false);
  const [activeDrawer, setActiveDrawer] = useState<LeftRailDrawer | null>(null);
  const [rightTab, setRightTab] = useState<RightPanelTabId>("code");
  const [toast, setToast] = useState<string | null>(null);
  const [graphHint] = useState<string[]>([]);
  const [codeTarget, setCodeTarget] = useState<CodeTarget | null>(null);
  const [graphNodes, setGraphNodes] = useState<Map<string, GraphNode>>(
    () => new Map()
  );

  const graphNodesRef = useRef(graphNodes);
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
  const [reconnectedPhase, setReconnectedPhase] = useState<
    "hidden" | "shown" | "fade"
  >("hidden");
  useEffect(() => {
    graphNodesRef.current = graphNodes;
  }, [graphNodes]);

  useEffect(() => {
    codePathRef.current = codeTarget?.path ?? null;
  }, [codeTarget?.path]);

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

  const openDrillDownFile = useCallback((p: string) => {
    setCodeTarget({ path: p });
    setRightTab("code");
  }, []);

  const openDrillDownNode = useCallback((nodeId: string) => {
    const n = graphNodesRef.current.get(nodeId);
    if (!n || !n.file_path) {
      // eslint-disable-next-line no-console
      console.error("node not found:", nodeId);
      return;
    }
    setCodeTarget({
      nodeId: n.id,
      path: n.file_path,
      lineStart: n.line_start,
      lineEnd: n.line_end,
      name: n.name,
    });
  }, []);

  const onT1GraphNodes = useCallback((list: GraphNode[]) => {
    setGraphNodes((prev) => {
      const next = new Map(prev);
      for (const n of list) {
        next.set(n.id, n);
      }
      return next;
    });
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
        if (m.type === "bootstrap_complete" && !hasBootstrappedRef.current) {
          hasBootstrappedRef.current = true;
          setBootstrapPhase("hiding");
          if (bootstrapHideTimerRef.current != null) {
            clearTimeout(bootstrapHideTimerRef.current);
          }
          bootstrapHideTimerRef.current = setTimeout(() => {
            bootstrapHideTimerRef.current = null;
            setBootstrapPhase("hidden");
          }, 200);
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
      openDrillDownNode(nodeId);
    };
    // eslint-disable-next-line no-console
    console.info("debug: window.__omnix_select_node(nodeId) ready");
    return () => {
      const w = window as unknown as { __omnix_select_node?: unknown };
      if (w.__omnix_select_node) delete w.__omnix_select_node;
    };
  }, [openDrillDownNode]);

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

  const onDrillSaveShell = useCallback(() => {
    setToast("Code tab save lands next");
    setTimeout(() => setToast(null), 2200);
  }, []);

  const pName = projectLabel(projectPath);

  const drawerContent: Record<LeftRailDrawer, ReactNode> = {
    files: <FilesDrawer workspaceId={workspaceId} onOpenFile={openDrillDownFile} />,
    search: <DrawerPlaceholder label="Search" />,
    bugs: <DrawerPlaceholder label="Bugs" />,
    receipts: <ReceiptsDrawer workspaceId={workspaceId} />,
    settings: <DrawerPlaceholder label="Settings" />,
  };

  const rightTabs: RightPanelTab[] = [
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

  useStudioKeybindings({
    drillOpen: codeTarget != null,
    onEscape: () => {
      if (activeDrawer) {
        setActiveDrawer(null);
        return true;
      }
      if (newFile) {
        setNewFile(false);
        return true;
      }
      return false;
    },
    onTogglePicker: () =>
      setActiveDrawer((drawer) => (drawer === "search" ? null : "search")),
    onNewFile: () => setNewFile(true),
    onCmdSWhenNoDrill: onDrillSaveShell,
    onSaveDrill: () => codeRef.current?.save(),
  });

  return (
    <div className="omnix-hex-bg relative h-full min-h-0 w-full font-sans text-omnix-text-primary">
      <LeftRail
        active={activeDrawer}
        onSelect={setActiveDrawer}
        onClose={() => setActiveDrawer(null)}
      >
        {activeDrawer ? drawerContent[activeDrawer] : null}
      </LeftRail>

      <nav
        className="pointer-events-none fixed left-1/2 top-5 z-[30] w-[min(100%-2rem,720px)] -translate-x-1/2 px-4 text-center"
        aria-label="Breadcrumb"
      >
        <div
          className="omnix-glass pointer-events-auto mx-auto flex w-max max-w-full items-center justify-center gap-1.5 rounded-full border border-omnix-accent-indigo/25 px-4 py-2 font-mono text-xs"
          id="breadcrumb"
        >
          <button
            type="button"
            onClick={onBack}
            className="text-omnix-text-muted transition hover:rounded-md hover:bg-[rgba(99,102,241,0.15)] hover:text-omnix-text-primary"
          >
            OMNIX
          </button>
          <span className="text-omnix-text-sep select-none">›</span>
          <span
            className="max-w-[min(50vw,24rem)] truncate text-omnix-text-primary"
            title={projectPath}
          >
            {pName}
          </span>
        </div>
      </nav>

      <div className="pointer-events-none fixed right-5 top-5 z-30" aria-label="Graph stats">
        <StatsPanel stats={stats} />
      </div>

      <ReconnectIndicator mode={reconnectIndicatorMode} />
      <BootstrapIndicator phase={bootstrapIndicatorPhase} />

      <div className="flex h-full min-h-0 w-full min-w-0 flex-col">
        <div className="relative min-h-0 w-full min-w-0 flex-1">
          <main className="flex h-full min-h-0 w-full min-w-0 flex-col p-3 pt-14">
            <div className="mb-2 text-[10px] font-mono font-medium uppercase tracking-[0.15em] text-omnix-text-dim">
              graph
            </div>
            <div
              className="relative min-h-0 min-w-0 flex-1 overflow-hidden rounded-lg border border-omnix-accent-indigo/20 bg-[rgba(2,6,21,0.5)]"
            >
              <GraphCanvas
                ref={graphRef}
                drillDownNodeId={codeTarget?.nodeId ?? null}
                onFunctionNodeClick={openDrillDownNode}
                onT1GraphNodes={onT1GraphNodes}
                onFileOrDirClick={openDrillDownFile}
                onDeselect={() => undefined}
              />
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
        onSelectTab={setRightTab}
        onNewAgentTab={() => showToastStable("Agent tabs land in slice 15", 1800)}
      />

      <div
        className="pointer-events-none fixed bottom-20 left-0 right-0 z-40 flex justify-center px-3 pl-12"
        role="search"
        aria-label="Find in project"
      >
        <div className="pointer-events-auto w-full max-w-2xl">
          <FindBar
            value={find}
            onChange={setFind}
            onClear={find ? () => setFind("") : undefined}
          />
        </div>
      </div>

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
          className="omnix-glass pointer-events-none fixed bottom-12 left-1/2 z-[60] -translate-x-1/2 rounded-md border border-omnix-accent-indigo/25 px-3 py-1.5 text-xs text-omnix-text-primary shadow-omnix-glass"
        >
          {toast}
        </div>
      )}
    </div>
  );
}
