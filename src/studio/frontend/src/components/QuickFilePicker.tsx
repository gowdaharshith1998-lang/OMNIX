import { useEffect, useMemo, useRef } from "react";
import type { FileEntry } from "@/lib/api";

type Props = {
  open: boolean;
  files: FileEntry[];
  filter: string;
  onClose: () => void;
  onPick: (path: string) => void;
};

export function QuickFilePicker({
  open,
  files,
  filter,
  onClose,
  onPick,
}: Props) {
  const listRef = useRef<HTMLUListElement>(null);
  const q = filter.trim().toLowerCase();
  const rows = useMemo(
    () =>
      files.filter((f) => f.path.toLowerCase().includes(q)).slice(0, 50),
    [files, q]
  );

  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", h);
    return () => window.removeEventListener("keydown", h);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-24"
      onMouseDown={onClose}
    >
      <div
        className="w-full max-w-lg rounded-lg border border-studio-line bg-studio-panel p-0 shadow-2xl"
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Quick file picker"
      >
        <div className="border-b border-studio-line px-3 py-2 text-xs text-studio-muted">
          Open file <span className="text-slate-500">— project</span>
        </div>
        <ul
          ref={listRef}
          className="max-h-64 overflow-y-auto text-sm text-slate-200"
        >
          {rows.length === 0 && (
            <li className="px-3 py-2 text-studio-muted">No matches</li>
          )}
          {rows.map((f) => (
            <li key={f.path}>
              <button
                type="button"
                className="w-full cursor-pointer px-3 py-1.5 text-left font-mono text-xs hover:bg-white/5"
                onClick={() => {
                  onPick(f.path);
                  onClose();
                }}
              >
                {f.path}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
