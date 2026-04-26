import { useCallback, useEffect, useState } from "react";
import { createFile, listFiles, type FileEntry } from "@/lib/api";
import { StudioWebSocket } from "@/lib/ws";
import { BottomToolbar } from "./BottomToolbar";
import { DrillDown } from "./DrillDown";
import { FindBar } from "./FindBar";
import { NewFileModal } from "./NewFileModal";
import { QuickFilePicker } from "./QuickFilePicker";
import { StatsPanel } from "./StatsPanel";

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

function isMod(e: KeyboardEvent) {
  return e.metaKey || e.ctrlKey;
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
  const [sel, setSel] = useState<{
    id: string;
    name: string;
    type: string;
    file_path?: string | null;
  } | null>(null);

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
          const n = msg.node as Record<string, unknown>;
          if (typeof n.id === "string" && typeof n.name === "string" && typeof n.type === "string") {
            setSel({
              id: n.id,
              name: n.name,
              type: n.type,
              file_path: (n.file_path as string) ?? null,
            });
            setGraphHint((h) => [String(n.name), ...h].slice(0, 5));
          }
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
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setPicker(false);
        setNewFile(false);
      }
      if (!isMod(e)) return;
      const k = e.key.toLowerCase();
      if (k === "p") {
        e.preventDefault();
        setPicker((p) => !p);
      }
      if (k === "n") {
        e.preventDefault();
        setNewFile(true);
      }
      if (k === "s") {
        e.preventDefault();
        setToast("No editor file open (shell)");
        setTimeout(() => setToast(null), 2200);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

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

      <div className="flex min-h-0 flex-1">
        <main className="flex min-w-0 flex-1 flex-col p-3">
          <div className="mb-2 text-[10px] font-mono uppercase text-studio-muted">
            Graph
          </div>
          <div className="flex min-h-0 flex-1 items-center justify-center rounded-lg border-2 border-dashed border-studio-line/80 bg-black/20 p-6">
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
        <DrillDown node={sel} />
      </div>

      <BottomToolbar
        onGraph={() => setToast("Graph tools — next iteration")}
        onSearch={() => setPicker(true)}
        onSave={() => {
          setToast("No editor file open (shell)");
          setTimeout(() => setToast(null), 2200);
        }}
      />

      <QuickFilePicker
        open={picker}
        files={files}
        filter={find}
        onClose={() => setPicker(false)}
        onPick={(p) => {
          setToast(`Picked ${p} (open in editor — next)`);
          setTimeout(() => setToast(null), 2400);
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
        <div className="fixed bottom-12 left-1/2 z-[60] -translate-x-1/2 rounded border border-studio-line bg-studio-panel px-3 py-1.5 text-xs text-slate-200 shadow-lg">
          {toast}
        </div>
      )}
    </div>
  );
}
