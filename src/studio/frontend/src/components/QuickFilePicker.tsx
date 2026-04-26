import { useEffect, useMemo, useRef, useState } from "react";
import type { FileEntry } from "@/lib/api";

type Props = {
  open: boolean;
  files: FileEntry[];
  filter: string;
  onFilterChange: (v: string) => void;
  onClose: () => void;
  /** Picked a file; drill-down and file list consumers should use this. */
  onFilePicked: (path: string) => void;
};

export function QuickFilePicker({
  open,
  files,
  filter,
  onFilterChange,
  onClose,
  onFilePicked,
}: Props) {
  const listRef = useRef<HTMLUListElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [sel, setSel] = useState(0);
  const q = filter.trim().toLowerCase();
  const rows = useMemo(
    () =>
      files.filter((f) => f.path.toLowerCase().includes(q)).slice(0, 50),
    [files, q]
  );
  useEffect(() => {
    setSel(0);
  }, [q, open, rows.length]);

  useEffect(() => {
    if (open) {
      queueMicrotask(() => inputRef.current?.focus());
    }
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const h = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
      if (e.key === "ArrowDown") {
        e.preventDefault();
        setSel((i) => Math.min(rows.length - 1, i + 1));
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        setSel((i) => Math.max(0, i - 1));
        return;
      }
      if (e.key === "Enter" && rows[sel]) {
        e.preventDefault();
        onFilePicked(rows[sel].path);
        onClose();
        return;
      }
    };
    window.addEventListener("keydown", h, true);
    return () => window.removeEventListener("keydown", h, true);
  }, [open, onClose, onFilePicked, rows, sel]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center bg-black/60 pt-20 backdrop-blur-sm"
      onMouseDown={onClose}
    >
      <div
        className="omnix-glass w-full max-w-lg overflow-hidden rounded-xl border border-omnix-accent-indigo/20 shadow-2xl"
        onMouseDown={(e) => e.stopPropagation()}
        role="dialog"
        aria-label="Quick file picker"
      >
        <div className="border-b border-omnix-accent-indigo/20 px-3 py-2 font-mono text-xs text-omnix-text-muted">
          open file <span className="text-omnix-text-dim/90">— project</span>
        </div>
        <div className="border-b border-omnix-accent-indigo/15 p-2">
          <input
            ref={inputRef}
            className="w-full rounded-md border border-slate-400/20 bg-[rgba(2,6,23,0.5)] px-2 py-1.5 font-mono text-sm text-omnix-text-primary outline-none focus:border-omnix-accent-indigo/65 focus:shadow-omnix-glow-cyan"
            value={filter}
            onChange={(e) => onFilterChange(e.target.value)}
            placeholder="Filter…"
            spellCheck={false}
            aria-label="Filter files"
          />
        </div>
        <ul
          ref={listRef}
          className="max-h-64 overflow-y-auto text-sm text-omnix-text-primary"
        >
          {rows.length === 0 && (
            <li className="px-3 py-2 text-omnix-text-dim">No matches</li>
          )}
          {rows.map((f, i) => (
            <li key={f.path}>
              <button
                type="button"
                className={
                  "w-full cursor-pointer border-l-2 py-1.5 pl-3 pr-3 text-left font-mono text-xs transition " +
                  (i === sel
                    ? "border-omnix-accent-indigo bg-[rgba(99,102,241,0.1)] text-omnix-text-primary shadow-omnix-glow"
                    : "border-transparent hover:bg-[rgba(99,102,241,0.08)] hover:shadow-omnix-glow")
                }
                onClick={() => {
                  onFilePicked(f.path);
                  onClose();
                }}
                onMouseEnter={() => setSel(i)}
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
