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
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onMouseDown={onClose}
    >
      <div
        className="omnix-glass w-full max-w-md rounded-xl border border-omnix-accent-indigo/20 p-4 shadow-2xl"
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="New file"
      >
        <h2 className="mb-3 font-sans text-sm font-medium text-omnix-text-primary">New file</h2>
        <label className="mb-1 block text-[10px] font-medium uppercase tracking-wide text-omnix-text-muted">
          Path (relative)
        </label>
        <input
          className="mb-2 w-full rounded-md border border-slate-400/20 bg-[rgba(2,6,23,0.5)] px-2 py-1.5 font-mono text-xs text-omnix-text-primary outline-none focus:border-omnix-accent-indigo/60 focus:shadow-omnix-glow-cyan"
          value={path}
          onChange={(e) => setPath(e.target.value)}
        />
        <label className="mb-1 block text-[10px] font-medium uppercase tracking-wide text-omnix-text-muted">
          Content
        </label>
        <textarea
          className="mb-3 h-28 w-full resize-none rounded-md border border-slate-400/20 bg-[rgba(2,6,23,0.5)] p-2 font-mono text-xs text-omnix-text-primary outline-none focus:border-omnix-accent-indigo/60 focus:shadow-omnix-glow-cyan"
          value={content}
          onChange={(e) => setContent(e.target.value)}
        />
        {err && <p className="mb-2 text-xs text-[--omnix-err]">{err}</p>}
        <div className="flex justify-end gap-2">
          <button
            type="button"
            className="omnix-glass cursor-pointer rounded-md border px-3 py-1 text-xs text-omnix-text-muted transition hover:text-omnix-text-primary"
            onClick={onClose}
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={busy}
            className="cursor-pointer rounded-md border border-omnix-accent-indigo/60 bg-omnix-accent-indigo/25 px-3 py-1 text-xs text-white transition hover:bg-omnix-accent-indigo/40 disabled:opacity-50"
            onClick={() => void submit()}
          >
            {busy ? "…" : "Create"}
          </button>
        </div>
      </div>
    </div>
  );
}
