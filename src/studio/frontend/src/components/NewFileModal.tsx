import { useEffect, useState } from "react";

const DEFAULT_PATH = "new_file.py";
const DEFAULT_CONTENT = "# new file\n";

type Props = {
  open: boolean;
  onClose: () => void;
  onCreate: (relPath: string, content: string) => Promise<void>;
};

export function NewFileModal({ open, onClose, onCreate }: Props) {
  const [path, setPath] = useState(DEFAULT_PATH);
  const [content, setContent] = useState(DEFAULT_CONTENT);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (open) {
      setPath(DEFAULT_PATH);
      setContent(DEFAULT_CONTENT);
      setErr(null);
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);

  if (!open) return null;

  const submit = async () => {
    setErr(null);
    setBusy(true);
    try {
      await onCreate(path.replace(/^\//, ""), content);
      onClose();
    } catch {
      setErr("Could not create file");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4"
      onMouseDown={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-studio-line bg-studio-panel p-4 shadow-2xl"
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="New file"
      >
        <h2 className="mb-3 text-sm font-medium text-white">New file</h2>
        <label className="mb-1 block text-[10px] uppercase text-studio-muted">
          Path (relative)
        </label>
        <input
          className="mb-2 w-full rounded border border-studio-line bg-black/30 px-2 py-1 font-mono text-xs text-white outline-none"
          value={path}
          onChange={(e) => setPath(e.target.value)}
        />
        <label className="mb-1 block text-[10px] uppercase text-studio-muted">
          Content
        </label>
        <textarea
          className="mb-3 h-28 w-full resize-none rounded border border-studio-line bg-black/30 p-2 font-mono text-xs text-white outline-none"
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
        {err && <p className="mb-2 text-xs text-rose-400">{err}</p>}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="rounded border border-studio-line px-3 py-1 text-xs text-slate-300 hover:bg-white/5"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={busy}
            className="rounded border border-sky-600 bg-sky-600/30 px-3 py-1 text-xs text-white hover:bg-sky-500/40 disabled:opacity-50"
            onClick={() => void submit()}
          >
            {busy ? "…" : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}
