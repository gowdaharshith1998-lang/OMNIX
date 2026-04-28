import { useCallback, useEffect, useRef, useState } from "react";
import { GraphCanvas, type GraphCanvasHandle } from "./Graph/GraphCanvas";
import { createFile, listFiles, type FileEntry } from "@/lib/api";
import { isT1Mode } from "@/lib/t1Mode";
import { StudioWebSocket } from "@/lib/ws";
import { useStudioKeybindings } from "@/lib/keybindings";
import { BottomToolbar } from "./BottomToolbar";
import { DrillDown, type DrillDownHandle } from "./DrillDown";
import { FindBar } from "./FindBar";
import { LeftIconStrip } from "./LeftIconStrip";
import { NewFileModal } from "./NewFileModal";
import { QuickFilePicker } from "./QuickFilePicker";
import { StatsPanel } from "./StatsPanel";
import { BootstrapIndicator } from "./BootstrapIndicator";
import {
  ReconnectIndicator,
  type ReconnectIndicatorMode,
} from "./ReconnectIndicator";
import type { DrillDownTarget, GraphNode } from "@/types/drilldown";

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

function headBadgeFor(
  t: DrillDownTarget,
  nodeType: string | undefined
): string {
  if (t.mode === "file") return "FILE";
  const u = (nodeType || "symbol").toLowerCase();
  if (u.includes("dir")) return "DIRECTORY";
  if (u === "function" || u === "method") return "FUNCTION";
  if (u === "class") return "CLASS";
  return u.replace(/[\s_]+/g, " ").toUpperCase().slice(0, 22);
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
  const [files, setFiles] = useState<FileEntry[]>([]);
  const [picker, setPicker] = useState(false);
  const [newFile, setNewFile] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [toast, setToast] = useState<string | null>(null);
  const [graphHint] = useState<string[]>([]);
  const [drillDownTarget, setDrillDownTarget] = useState<DrillDownTarget | null>(
    null
  );
  const [graphNodes, setGraphNodes] = useState<Map<string, GraphNode>>(
    () => new Map()
  );
  const [externalFileEpoch] = useState(0);

  const graphNodesRef = useRef(graphNodes);
  const graphRef = useRef<GraphCanvasHandle | null>(null);
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

  const drillDownRef = useRef<DrillDownHandle | null>(null);
  const drillFileRef = useRef<string | null>(null);
  useEffect(() => {
    if (!drillDownTarget) {
      drillFileRef.current = null;
      return;
    }
    drillFileRef.current =
      drillDownTarget.mode === "file"
        ? drillDownTarget.path
        : drillDownTarget.filePath;
  }, [drillDownTarget]);

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
    setDrillDownTarget({ mode: "file", path: p });
  }, []);

  const openDrillDownNode = useCallback((nodeId: string) => {
    const n = graphNodesRef.current.get(nodeId);
    if (!n || !n.file_path) {
      // eslint-disable-next-line no-console
      console.error("node not found:", nodeId);
      return;
    }
    setDrillDownTarget({
      mode: "node",
      nodeId: n.id,
      filePath: n.file_path,
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

  const closeDrillDown = useCallback(() => {
    setDrillDownTarget(null);
  }, []);

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
  }, [workspaceId]);

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
    if (drillDownTarget?.mode !== "node") return;
    const id = drillDownTarget.nodeId;
    const inMap = graphNodes.get(id);
    if (!inMap) return;
    if (
      inMap.line_start !== drillDownTarget.lineStart ||
      inMap.line_end !== drillDownTarget.lineEnd
    ) {
      setDrillDownTarget((prev) => {
        if (!prev || prev.mode !== "node" || prev.nodeId !== id) return prev;
        return {
          ...prev,
          lineStart: inMap.line_start,
          lineEnd: inMap.line_end,
        };
      });
    }
  }, [drillDownTarget, graphNodes]);

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
    setToast("No editor file open (shell)");
    setTimeout(() => setToast(null), 2200);
  }, []);

  const onGraphDeselect = useCallback(() => {
    if (drillDownTarget) {
      closeDrillDown();
    }
  }, [drillDownTarget, closeDrillDown]);

  const pName = projectLabel(projectPath);
  const headBadge = drillDownTarget
    ? headBadgeFor(
        drillDownTarget,
        drillDownTarget.mode === "node"
          ? graphNodes.get(drillDownTarget.nodeId)?.type
          : undefined
      )
    : "FILE";

  const stripActive =
    settingsOpen ? "settings" : picker ? "find" : (null as "find" | "settings" | "project" | null);

  useStudioKeybindings({
    drillOpen: drillDownTarget != null,
    onEscape: () => {
      if (settingsOpen) {
        setSettingsOpen(false);
        return true;
      }
      if (drillDownTarget) {
        closeDrillDown();
        return true;
      }
      if (newFile) {
        setNewFile(false);
        return true;
      }
      if (picker) {
        setPicker(false);
        return true;
      }
      return false;
    },
    onTogglePicker: () => setPicker((p) => !p),
    onNewFile: () => setNewFile(true),
    onCmdSWhenNoDrill: onDrillSaveShell,
    onSaveDrill: () => drillDownRef.current?.save(),
  });

  return (
    <div className="omnix-hex-bg relative h-full min-h-0 w-full pl-12 font-sans text-omnix-text-primary">
      <LeftIconStrip
        projectPath={projectPath}
        active={stripActive}
        onOpenFind={() => setPicker(true)}
        onOpenSettings={() => setSettingsOpen((s) => !s)}
        onProject={async () => {
          try {
            await navigator.clipboard.writeText(projectPath);
            showToastStable("Project path copied", 1500);
          } catch {
            showToastStable(projectPath, 3000);
          }
        }}
      />

      {settingsOpen && (
        <>
          <button
            type="button"
            className="fixed inset-0 z-[50] border-0 bg-black/50 backdrop-blur-[2px] cursor-default"
            aria-label="Close settings"
            onClick={() => setSettingsOpen(false)}
          />
          <aside
            className="fixed left-12 top-0 z-[60] box-border flex h-full w-[min(360px,90vw-3rem)] flex-col border-r border-omnix-sb-border bg-omnix-bg shadow-[8px_0_32px_rgba(0,0,0,0.35)]"
            aria-label="Settings"
          >
            <div className="flex items-center justify-between border-b border-omnix-sb-border px-3 py-2.5">
              <h2 className="text-sm font-semibold text-omnix-sb-text">Settings</h2>
              <button
                type="button"
                className="h-7 w-7 cursor-pointer rounded border border-omnix-sb-border bg-omnix-panel text-omnix-sb-muted text-base leading-none hover:text-omnix-sb-text"
                onClick={() => setSettingsOpen(false)}
                aria-label="Close settings"
                title="Close"
              >
                ✕
              </button>
            </div>
            <div className="overflow-auto p-3 text-sm text-omnix-sb-text">
              <p className="text-omnix-sb-muted">
                Settings — coming Day 14+ (placeholders, providers, and agent wiring).
              </p>
            </div>
          </aside>
        </>
      )}

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
              className={
                "relative min-h-0 min-w-0 flex-1 overflow-hidden rounded-lg border border-omnix-accent-indigo/20 bg-[rgba(2,6,21,0.5)]" +
                (drillDownTarget
                  ? " pr-[min(40%,32rem)] transition-[padding] max-md:pr-0"
                  : "")
              }
            >
              <GraphCanvas
                ref={graphRef}
                drillDownNodeId={
                  drillDownTarget?.mode === "node" ? drillDownTarget.nodeId : null
                }
                onFunctionNodeClick={openDrillDownNode}
                onT1GraphNodes={onT1GraphNodes}
                onFileOrDirClick={() => {
                  /* X-RAY in Day 12; engine also logs */
                }}
                onDeselect={onGraphDeselect}
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

          <div
            className={
              drillDownTarget
                ? "pointer-events-auto flex h-full min-h-0 w-[min(40%,32rem)] min-w-0 max-w-[min(40%,90vw)] shrink-0 flex-col border-omnix-sb-border"
                : "pointer-events-none w-0 max-w-0 shrink-0 overflow-hidden"
            }
            style={drillDownTarget ? { position: "absolute", right: 0, top: 0, bottom: 0, zIndex: 25 } : undefined}
          >
            {drillDownTarget && (
              <DrillDown
                key={
                  drillDownTarget.mode === "file"
                    ? "f:" + drillDownTarget.path
                    : "n:" + drillDownTarget.nodeId
                }
                ref={drillDownRef}
                headBadge={headBadge}
                workspaceId={workspaceId}
                target={drillDownTarget}
                onClose={closeDrillDown}
                onToast={showToastStable}
                externalFileEpoch={externalFileEpoch}
              />
            )}
          </div>
        </div>
      </div>

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

      <QuickFilePicker
        open={picker}
        files={files}
        filter={find}
        onFilterChange={setFind}
        onClose={() => setPicker(false)}
        onFilePicked={(p) => {
          openDrillDownFile(p);
        }}
      />
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
