import { useEffect, useState } from "react";
import { getStudioInitial, listRecent, type RecentItem } from "@/lib/api";

type Props = {
  onOpenPath: (path: string) => void;
  busy: boolean;
};

export function Welcome({ onOpenPath, busy }: Props) {
  const [path, setPath] = useState("");
  const [recent, setRecent] = useState<RecentItem[]>([]);
  const [hint, setHint] = useState<string | null>(null);

  useEffect(() => {
    void (async () => {
      try {
        const [init, rec] = await Promise.all([getStudioInitial(), listRecent()]);
        if (init.path) setPath(init.path);
        setRecent(rec);
      } catch {
        setHint("Could not load recent / initial path");
      }
    })();
  }, []);

  return (
    <div className="omnix-hex-bg flex min-h-full min-w-0 flex-col items-center justify-center px-4">
      <div className="omnix-glass w-full max-w-md rounded-xl border border-omnix-accent-indigo/20 p-6 shadow-omnix-glow">
        <div className="mb-6 text-center">
          <h1
            className="font-mono text-2xl font-semibold tracking-tight text-omnix-text-primary"
            style={{
              textShadow: "0 0 20px rgba(99, 102, 241, 0.25), 0 0 2px rgba(99, 102, 241, 0.4)",
            }}
          >
            OMNIX Studio
          </h1>
          <p className="mt-1 font-sans text-sm text-omnix-text-dim">
            Code graph — local workspace
          </p>
        </div>

        <div className="space-y-3">
          <label className="block text-[10px] font-medium uppercase tracking-wide text-omnix-text-muted">
            Project path
          </label>
          <input
            className="w-full rounded-md border border-slate-400/20 bg-[rgba(2,6,23,0.45)] px-3 py-2 font-mono text-sm text-omnix-text-primary outline-none transition-[border-color,box-shadow] focus:border-omnix-accent-indigo/60 focus:shadow-omnix-glow-cyan"
            value={path}
            onChange={(e) => setPath(e.target.value)}
            placeholder="/path/to/project"
            spellCheck={false}
          />
          <div className="flex flex-wrap gap-2">
            <button
              type="button"
              disabled={busy || !path.trim()}
              onClick={() => onOpenPath(path.trim())}
              className="cursor-pointer rounded-md border border-omnix-accent-indigo/55 bg-omnix-accent-indigo/20 px-4 py-2 text-sm text-white transition hover:border-omnix-accent-indigo hover:bg-omnix-accent-indigo/30 disabled:cursor-not-allowed disabled:opacity-40"
            >
              Open folder
            </button>
          </div>
        </div>

        {hint && <p className="mt-3 text-xs text-[--omnix-err]">{hint}</p>}

        {recent.length > 0 && (
          <div className="mt-5 border-t border-omnix-accent-indigo/15 pt-3">
            <div className="mb-1 text-[10px] font-medium uppercase tracking-wide text-omnix-text-muted">
              Recent
            </div>
            <ul className="max-h-40 space-y-0.5 overflow-y-auto text-left">
              {recent.map((r) => (
                <li key={r.path}>
                  <button
                    type="button"
                    className="w-full truncate rounded-md px-1.5 py-0.5 text-left font-mono text-xs text-omnix-cyan/90 transition hover:bg-[rgba(99,102,241,0.12)] hover:shadow-omnix-glow disabled:opacity-50"
                    onClick={() => onOpenPath(r.path)}
                    disabled={busy}
                    title={r.path}
                  >
                    {r.path}
                  </button>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </div>
  );
}
