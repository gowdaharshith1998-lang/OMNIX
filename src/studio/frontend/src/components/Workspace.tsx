import { useCallback, useEffect, useRef, useState } from "react";
import { createFile, listFiles, type FileEntry } from "@/lib/api";
import { StudioWebSocket } from "@/lib/ws";
import { useStudioKeybindings } from "@/lib/keybindings";
import { applyNodeModified } from "@/lib/graphNode";
import { BottomToolbar } from "./BottomToolbar";
import { DrillDown, type DrillDownHandle } from "./DrillDown";
import { FindBar } from "./FindBar";
import { NewFileModal } from "./NewFileModal";
import { QuickFilePicker } from "./QuickFilePicker";
import { StatsPanel } from "./StatsPanel";
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

function recordFromNodePayload(n: Record<string, unknown>): GraphNode | null {
  if (typeof n.id !== "string" || typeof n.name !== "string" || typeof n.type !== "string") {
    return null;
  }
  return {
    id: n.id,
    name: n.name,
    type: n.type,
    file_path: typeof n.file_path === "string" ? n.file_path : null,
    line_start: typeof n.line_start === "number" ? n.line_start : 0,
    line_end: typeof n.line_end === "number" ? n.line_end : 0,
  };
}

export function Workspace({
  workspaceId,
  projectPath,
  initialStats,
  onBack,
}: Props) {
  const [find, setFind] = useState("");
  const [stats, setStats] = useState({
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
  const [toast, setToast] = useState<string | null>(null);
  const [graphHint, setGraphHint] = useState<string[]>([]);
  const [drillDownTarget, setDrillDownTarget] = useState<DrillDownTarget | null>(
    null
  );
  const [graphNodes, setGraphNodes] = useState<Map<string, GraphNode>>(
    () => new Map()
  );
  const [externalFileEpoch, setExternalFileEpoch] = useState(0);

  const graphNodesRef = useRef(graphNodes);
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

  const closeDrillDown = useCallback(() => {
    setDrillDownTarget(null);
  }, []);

  useEffect(() => {
    const c = new StudioWebSocket(
      workspaceId,
      (msg) => {
        if (msg.type === "stats" && typeof msg.files === "number") {
          setStats({
            files: msg.files as number,
            functions: msg.functions as number,
            classes: msg.classes as number,
            edges: msg.edges as number,
            dark_matter: (msg.dark_matter as number) ?? 0,
            entangled: (msg.entangled as number) ?? 0,
          });
        }
        if (msg.type === "node_added" && msg.node && typeof msg.node === "object") {
          const rec = recordFromNodePayload(
            msg.node as Record<string, unknown>
          );
          if (rec) {
            setGraphNodes((prev) => {
              const next = new Map(prev);
              next.set(rec.id, rec);
              return next;
            });
            setGraphHint((h) => [String(rec.name), ...h].slice(0, 5));
            if (rec.file_path === drillFileRef.current) {
              queueMicrotask(() =>
                setExternalFileEpoch((e) => e + 1)
              );
            }
          }
        }
        if (msg.type === "node_modified" && msg.node_id) {
          const nid = String(msg.node_id);
          const ch = msg.changes as
            | Record<string, { old?: unknown; new?: unknown }>
            | undefined;
          setGraphNodes((prev) => {
            const next = new Map(prev);
            const cur = next.get(nid);
            if (cur) {
              const u = applyNodeModified(cur, ch);
              next.set(nid, u);
              if (u.file_path === drillFileRef.current) {
                queueMicrotask(() =>
                  setExternalFileEpoch((e) => e + 1)
                );
              }
            }
            return next;
          });
        }
        if (msg.type === "node_removed" && msg.node_id) {
          const id = String(msg.node_id);
          setGraphNodes((prev) => {
            const next = new Map(prev);
            next.delete(id);
            return next;
          });
        }
        if (msg.type === "file_added" && typeof msg.path === "string") {
          void refreshFiles();
        }
      },
      (s) => {
        if (s === "connecting") setWsState("connecting");
        if (s === "open") setWsState("open");
        if (s === "closed") setWsState("closed");
      }
    );
    c.connect();
    return () => c.close();
  }, [workspaceId, refreshFiles]);

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

  useStudioKeybindings({
    drillOpen: drillDownTarget != null,
    onEscape: () => {
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
    <div className="studio-hex-bg flex h-full flex-col text-slate-200">
      <header className="flex shrink-0 items-center justify-between gap-2 border-b border-studio-line bg-black/40 px-3 py-2">
        <div className="min-w-0">
          <button
            type="button"
            onClick={onBack}
            className="mr-2 text-[10px] uppercase text-studio-muted hover:text-white"
          >
            ← Back
          </button>
          <span className="truncate font-mono text-xs text-slate-300">
            {projectPath}
          </span>
        </div>
        <StatsPanel stats={stats} wsState={wsState} />
      </header>

      <div className="flex shrink-0 border-b border-studio-line bg-black/20 px-3 py-2">
        <FindBar value={find} onChange={setFind} />
      </div>

      <div className="relative flex min-h-0 min-w-0 flex-1">
        <main className="flex min-w-0 min-h-0 flex-1 flex-col p-3">
          <div className="mb-2 text-[10px] font-mono uppercase text-studio-muted">
            Graph
          </div>
          <div className="flex min-h-0 min-w-0 flex-1 items-center justify-center rounded-lg border-2 border-dashed border-studio-line/80 bg-black/20 p-6">
            <div className="max-w-md text-center">
              <p className="text-sm text-slate-300">
                Graph canvas <span className="text-studio-muted">(Day 10 shell)</span>
              </p>
              {graphHint.length > 0 && (
                <p className="mt-2 font-mono text-xs text-slate-500">
                  recent: {graphHint.join(" · ")}
                </p>
              )}
            </div>
          </div>
        </main>

        <div
          className={
            drillDownTarget
              ? "flex h-full min-h-0 w-[min(32rem,46vw)] min-w-0 max-w-[min(32rem,90vw)] shrink-0 flex-col transition-all duration-200"
              : "h-full w-0 max-w-0 shrink-0 flex-col overflow-hidden"
          }
        >
          {drillDownTarget && (
            <DrillDown
              key={
                drillDownTarget.mode === "file"
                  ? "f:" + drillDownTarget.path
                  : "n:" + drillDownTarget.nodeId
              }
              ref={drillDownRef}
              workspaceId={workspaceId}
              target={drillDownTarget}
              onClose={closeDrillDown}
              onToast={showToastStable}
              externalFileEpoch={externalFileEpoch}
            />
          )}
        </div>
      </div>

      <BottomToolbar
        onGraph={() => setToast("Graph tools — next iteration")}
        onSearch={() => setPicker(true)}
        onSave={() => {
          if (drillDownTarget) drillDownRef.current?.save();
          else onDrillSaveShell();
        }}
      />

      <QuickFilePicker
        open={picker}
        files={files}
        filter={find}
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
        <div className="pointer-events-none fixed bottom-12 left-1/2 z-[60] -translate-x-1/2 rounded border border-studio-line bg-studio-panel px-3 py-1.5 text-xs text-slate-200 shadow-lg">
          {toast}
        </div>
      )}
    </div>
  );
}
