import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
} from "react";
import Editor, { type OnMount } from "@monaco-editor/react";
import type { editor } from "monaco-editor";
import { FileConflictError, getFile, putFile } from "@/lib/api";

export type CodeTarget = {
  path: string;
  lineStart?: number;
  lineEnd?: number;
  nodeId?: string;
  name?: string;
};

export type CodeTabHandle = {
  save: () => void;
};

type Props = {
  workspaceId: string;
  target: CodeTarget | null;
  externalFileEpoch: number;
  onToast: (message: string, durationMs?: number) => void;
};

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

function basename(p: string) {
  const n = p.replace(/\\/g, "/").split("/").pop();
  return n || p;
}

export const CodeTab = forwardRef<CodeTabHandle, Props>(function CodeTab(
  { workspaceId, target, externalFileEpoch, onToast },
  ref
) {
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [path, setPath] = useState("");
  const [editorLang, setEditorLang] = useState("plaintext");
  const [editorValue, setEditorValue] = useState("");
  const [diskStale, setDiskStale] = useState(false);
  const editorRef = useRef<editor.IStandaloneCodeEditor | null>(null);
  const savedTextRef = useRef("");
  const dirtyRef = useRef(false);
  const lastMtimeRef = useRef(-1.0);
  const targetRef = useRef(target);
  const externalFileEpochRef = useRef(externalFileEpoch);
  const handledEpochRef = useRef(0);

  targetRef.current = target;
  externalFileEpochRef.current = externalFileEpoch;

  const scrollToTargetLine = useCallback(() => {
    const ed = editorRef.current;
    const line = targetRef.current?.lineStart;
    if (!ed || !line || line < 1) return;
    ed.revealLineInCenter(line);
    ed.setPosition({ lineNumber: line, column: 1 });
  }, []);

  const markDirty = useCallback((dirty: boolean) => {
    dirtyRef.current = dirty;
    if (dirty) setDiskStale(false);
  }, []);

  const load = useCallback(async () => {
    const t = targetRef.current;
    if (!t) {
      setPath("");
      setEditorValue("");
      savedTextRef.current = "";
      markDirty(false);
      return;
    }
    setLoading(true);
    setErr(null);
    setDiskStale(false);
    setPath(t.path);
    try {
      const result = await getFile(workspaceId, t.path);
      lastMtimeRef.current = result.last_modified;
      setEditorLang(toMonacoLanguage(result.language));
      savedTextRef.current = result.content;
      setEditorValue(result.content);
      editorRef.current?.setValue(result.content);
      markDirty(false);
      handledEpochRef.current = externalFileEpochRef.current;
      queueMicrotask(scrollToTargetLine);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "load failed");
    } finally {
      setLoading(false);
    }
  }, [markDirty, scrollToTargetLine, workspaceId]);

  useEffect(() => {
    void load();
  }, [target?.path, load]);

  useEffect(() => {
    scrollToTargetLine();
  }, [target?.lineStart, scrollToTargetLine]);

  const refreshFromDisk = useCallback(async () => {
    const t = targetRef.current;
    if (!t) return;
    if (dirtyRef.current) {
      setDiskStale(true);
      return;
    }
    const result = await getFile(workspaceId, t.path);
    lastMtimeRef.current = result.last_modified;
    setEditorLang(toMonacoLanguage(result.language));
    savedTextRef.current = result.content;
    setEditorValue(result.content);
    if (editorRef.current?.getValue() !== result.content) {
      editorRef.current?.setValue(result.content);
    }
    markDirty(false);
    queueMicrotask(scrollToTargetLine);
  }, [markDirty, scrollToTargetLine, workspaceId]);

  useEffect(() => {
    if (!target || loading || err) return;
    if (externalFileEpoch <= handledEpochRef.current) return;
    handledEpochRef.current = externalFileEpoch;
    void refreshFromDisk().catch(() => {
      setDiskStale(true);
    });
  }, [err, externalFileEpoch, loading, refreshFromDisk, target]);

  const save = useCallback(async () => {
    const t = targetRef.current;
    if (!t) {
      onToast("No file open", 1400);
      return;
    }
    const body = editorRef.current?.getValue() ?? editorValue;
    if (!dirtyRef.current) {
      onToast("saved", 1000);
      return;
    }
    try {
      const out = await putFile(workspaceId, t.path, body, lastMtimeRef.current);
      lastMtimeRef.current = out.new_last_modified;
      savedTextRef.current = body;
      setEditorValue(body);
      markDirty(false);
      handledEpochRef.current = externalFileEpoch;
      onToast("saved", 1000);
    } catch (e) {
      if (e instanceof FileConflictError) {
        setDiskStale(true);
        onToast("file changed externally", 3000);
      } else {
        onToast("Save failed", 2400);
      }
    }
  }, [editorValue, externalFileEpoch, markDirty, onToast, workspaceId]);

  useImperativeHandle(ref, () => ({ save: () => void save() }), [save]);

  const onMount: OnMount = (editor) => {
    editorRef.current = editor;
    scrollToTargetLine();
  };

  if (!target) {
    return (
      <div className="flex h-full items-center justify-center p-6 text-center text-sm text-omnix-text-dim">
        Select an entity in the brain to open the Code tab.
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="shrink-0 border-b border-[var(--omnix-shell-border)] px-3 py-2">
        <div className="truncate font-mono text-xs text-omnix-text-primary" title={path}>
          {basename(path)}
        </div>
        {target.name && (
          <div className="truncate font-mono text-[10px] text-omnix-text-dim">
            {target.name}
            {target.lineStart ? `:${target.lineStart}` : ""}
          </div>
        )}
      </div>
      {diskStale && (
        <div className="shrink-0 border-b border-amber-800/50 bg-amber-950/35 px-3 py-1 text-[10px] text-amber-200/90">
          file changed on disk; save is paused until you reload or resolve edits
        </div>
      )}
      <div className="min-h-0 flex-1">
        {err && <div className="p-3 text-sm text-rose-300/90">Load error: {err}</div>}
        {loading && !err && <div className="p-3 text-sm text-omnix-text-dim">Loading...</div>}
        {!loading && !err && (
          <Editor
            className="min-h-0 flex-1"
            key={path}
            defaultLanguage="plaintext"
            theme="omnix-dark"
            path={path}
            value={editorValue}
            onChange={(value) => {
              const next = value ?? "";
              setEditorValue(next);
              markDirty(next !== savedTextRef.current);
            }}
            language={editorLang}
            onMount={onMount}
            options={{
              minimap: { enabled: false },
              fontSize: 12,
              fontFamily: "JetBrains Mono, ui-monospace, monospace",
              scrollBeyondLastLine: false,
              automaticLayout: true,
              wordWrap: "on",
            }}
          />
        )}
      </div>
    </div>
  );
});
