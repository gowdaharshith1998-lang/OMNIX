import {
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  forwardRef,
} from "react";
import Editor, { type OnMount } from "@monaco-editor/react";
import type { DrillDownTarget } from "@/types/drilldown";
import { FileConflictError, getFile, putFile } from "@/lib/api";
import type { editor } from "monaco-editor";

type Props = {
  workspaceId: string;
  target: DrillDownTarget;
  onClose: () => void;
  onToast: (message: string, durationMs?: number) => void;
  /** Bumps when the open file is touched by a live graph delta. */
  externalFileEpoch: number;
};

export type DrillDownHandle = { save: () => void };

const tabBtn =
  "px-2 py-1 text-[10px] uppercase border-b-2 -mb-px transition-colors";
const tabActive = "border-sky-400 text-white";
const tabInert = "border-transparent text-studio-muted hover:text-slate-300";

function fileBasename(p: string) {
  const n = p.replace(/\\/g, "/").split("/").pop();
  return n || p;
}

function sliceByLines(content: string, start: number, end: number) {
  const lines = content.split("\n");
  return lines.slice(start - 1, end).join("\n");
}

function replaceLineRange(
  full: string,
  start: number,
  end: number,
  replacement: string
) {
  const lines = full.split("\n");
  const rlines = replacement.split("\n");
  return [...lines.slice(0, start - 1), ...rlines, ...lines.slice(end)].join(
    "\n"
  );
}

function toMonacoLanguage(grammar: string): string {
  const s = (grammar || "plaintext").toLowerCase();
  if (s === "python") return "python";
  if (s === "typescript" || s === "ts") return "typescript";
  if (s === "tsx" || s === "typescriptreact") return "typescript";
  if (s === "javascript" || s === "js") return "javascript";
  if (s === "jsx" || s === "javascriptreact") return "javascript";
  if (s === "json") return "json";
  if (s === "markdown" || s === "md") return "markdown";
  if (s === "rust" || s === "rs") return "rust";
  if (s === "go" || s === "golang") return "go";
  if (s === "c" || s === "cpp" || s === "c++") return "cpp";
  return "plaintext";
}

function loadKey(t: DrillDownTarget) {
  if (t.mode === "file") return `f:${t.path}`;
  return `n:${t.nodeId}:${t.lineStart}:${t.lineEnd}`;
}

export const DrillDown = forwardRef<DrillDownHandle, Props>(
  function DrillDown(
    { workspaceId, target, onClose, onToast, externalFileEpoch },
    ref
  ) {
    const [tab, setTab] = useState<"code" | "agent" | "history">("code");
    const [loading, setLoading] = useState(true);
    const [err, setErr] = useState<string | null>(null);
    const [editorLang, setEditorLang] = useState("plaintext");
    const [path, setPath] = useState<string>("");
    const lastMtimeRef = useRef(-1.0);
    const savedTextRef = useRef("");
    const [editorValue, setEditorValue] = useState("");
    const dirtyRef = useRef(false);
    const [diskStale, setDiskStale] = useState(false);
    const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
    const lastHandledEpoch = useRef(0);
    const extEpoch = useRef(externalFileEpoch);
    extEpoch.current = externalFileEpoch;
    const targetRef = useRef(target);
    targetRef.current = target;

    const markDirty = useCallback((d: boolean) => {
      dirtyRef.current = d;
      if (d) setDiskStale(false);
    }, []);

    const load = useCallback(async () => {
      setLoading(true);
      setErr(null);
      setDiskStale(false);
      const t = targetRef.current;
      const fp = t.mode === "file" ? t.path : t.filePath;
      setPath(fp);
      try {
        const r = await getFile(workspaceId, fp);
        lastMtimeRef.current = r.last_modified;
        setEditorLang(toMonacoLanguage(r.language));
        let show: string;
        if (t.mode === "file") {
          show = r.content;
        } else {
          show = sliceByLines(
            r.content,
            t.lineStart,
            t.lineEnd
          );
        }
        savedTextRef.current = show;
        setEditorValue(show);
        markDirty(false);
        lastHandledEpoch.current = extEpoch.current;
      } catch (e) {
        setErr((e as Error).message);
      } finally {
        setLoading(false);
      }
    }, [workspaceId, markDirty]);

    const editorKey = loadKey(target);

    useEffect(() => {
      setTab("code");
      void load();
    }, [target, load]);

    const onMount: OnMount = (editor) => {
      editorRef.current = editor;
    };

    const doSave = useCallback(async () => {
      if (!path) return;
      const ed = editorRef.current;
      const body = ed?.getValue() ?? editorValue;
      if (!dirtyRef.current) {
        onToast("saved", 1000);
        return;
      }
      const t = targetRef.current;
      const filePutPath = t.mode === "file" ? t.path : t.filePath;
      let outFull: string;
      if (t.mode === "file") {
        outFull = body;
      } else {
        const cur0 = await getFile(workspaceId, t.filePath);
        outFull = replaceLineRange(
          cur0.content,
          t.lineStart,
          t.lineEnd,
          body
        );
      }
      try {
        const out = await putFile(
          workspaceId,
          filePutPath,
          outFull,
          lastMtimeRef.current
        );
        lastMtimeRef.current = out.new_last_modified;
        if (t.mode === "file") {
          savedTextRef.current = body;
          ed?.setValue(body);
          setEditorValue(body);
        } else {
          const cur2 = await getFile(workspaceId, t.filePath);
          lastMtimeRef.current = cur2.last_modified;
          const nt = targetRef.current;
          if (nt.mode === "node") {
            const slice2 = sliceByLines(
              cur2.content,
              nt.lineStart,
              nt.lineEnd
            );
            savedTextRef.current = slice2;
            ed?.setValue(slice2);
            setEditorValue(slice2);
          }
        }
        markDirty(false);
        onToast("saved", 1000);
        lastHandledEpoch.current = extEpoch.current;
      } catch (e) {
        if (e instanceof FileConflictError) {
          onToast("file changed externally", 3000);
        } else {
          onToast("Save failed", 2400);
        }
      }
    }, [path, workspaceId, editorValue, onToast, markDirty]);

    useImperativeHandle(
      ref,
      () => ({ save: () => void doSave() }),
      [doSave]
    );

    const tryRefreshFromDisk = useCallback(async () => {
      if (dirtyRef.current) {
        setDiskStale(true);
        return;
      }
      const t = targetRef.current;
      const fp = t.mode === "file" ? t.path : t.filePath;
      const r = await getFile(workspaceId, fp);
      lastMtimeRef.current = r.last_modified;
      setEditorLang(toMonacoLanguage(r.language));
      let show: string;
      if (t.mode === "file") {
        show = r.content;
      } else {
        show = sliceByLines(r.content, t.lineStart, t.lineEnd);
      }
      const ed = editorRef.current;
      if (ed && ed.getValue() !== show) {
        ed.setValue(show);
      }
      setEditorValue(show);
      savedTextRef.current = show;
      markDirty(false);
    }, [workspaceId, markDirty]);

    useEffect(() => {
      if (loading || err) return;
      if (externalFileEpoch <= lastHandledEpoch.current) return;
      lastHandledEpoch.current = externalFileEpoch;
      void tryRefreshFromDisk().catch(() => {
        /* network */
      });
    }, [externalFileEpoch, loading, err, tryRefreshFromDisk]);

    const headerText =
      target.mode === "file"
        ? fileBasename(target.path)
        : `${target.name} — ${target.filePath}:${target.lineStart}-${target.lineEnd}`;

    return (
      <div className="flex h-full w-full min-h-0 min-w-0 flex-col border-l border-studio-line bg-studio-panel/90 shadow-xl">
        <div className="flex shrink-0 items-start justify-between gap-2 border-b border-studio-line px-2 py-1.5">
          <div className="min-w-0">
            <div className="font-mono text-[10px] uppercase text-studio-muted">
              Drill down
            </div>
            <div
              className="truncate font-mono text-xs text-slate-200"
              title={headerText}
            >
              {headerText}
            </div>
          </div>
          <button
            type="button"
            className="shrink-0 rounded border border-studio-line px-2 py-0.5 text-[10px] text-slate-400 hover:border-white/30 hover:text-white"
            onClick={onClose}
            aria-label="Close drill down"
          >
            ✕
          </button>
        </div>

        <div className="flex shrink-0 border-b border-studio-line px-1">
          <button
            type="button"
            className={`${tabBtn} ${tab === "code" ? tabActive : tabInert}`}
            onClick={() => setTab("code")}
          >
            Code
          </button>
          <button
            type="button"
            className={`${tabBtn} ${tab === "agent" ? tabActive : tabInert}`}
            onClick={() => setTab("agent")}
          >
            Agent
          </button>
          <button
            type="button"
            className={`${tabBtn} ${
              tab === "history" ? tabActive : tabInert
            }`}
            onClick={() => setTab("history")}
          >
            History
          </button>
        </div>

        {diskStale && (
          <div className="shrink-0 border-b border-amber-700/50 bg-amber-950/40 px-2 py-1 text-[10px] text-amber-200/90">
            file changed on disk — reload to discard your edits
          </div>
        )}

        <div className="min-h-0 min-w-0 flex-1">
          {tab === "code" && (
            <div className="flex h-full min-h-0 w-full min-w-0 flex-col">
              {err && (
                <div className="p-2 text-rose-300/90">Load error: {err}</div>
              )}
              {loading && !err && (
                <div className="p-2 text-studio-muted">Loading…</div>
              )}
              {!loading && !err && (
                <Editor
                  className="min-h-0 flex-1"
                  key={editorKey}
                  defaultLanguage="plaintext"
                  path={path + "?" + editorKey}
                  value={editorValue}
                  onChange={(v) => {
                    setEditorValue(v ?? "");
                    const clean = (v ?? "") === savedTextRef.current;
                    markDirty(!clean);
                  }}
                  language={editorLang}
                  onMount={onMount}
                  options={{
                    minimap: { enabled: false },
                    fontSize: 12,
                    scrollBeyondLastLine: false,
                    automaticLayout: true,
                    wordWrap: "on",
                  }}
                />
              )}
            </div>
          )}

          {tab === "agent" && (
            <div className="p-3 text-studio-muted">Agent comes Day 14</div>
          )}

          {tab === "history" && (
            <div className="p-3 text-studio-muted">History comes Day 16</div>
          )}
        </div>
      </div>
    );
  }
);
DrillDown.displayName = "DrillDown";
