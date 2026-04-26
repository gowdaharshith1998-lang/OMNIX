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
    <div className="flex min-h-full flex-col items-center justify-center px-4">
      <div className="mb-10 text-center">
        <h1 className="text-2xl font-semibold tracking-tight text-white">
          OMNIX Studio
        </h1>
        <p className="mt-1 text-sm text-studio-muted">
          Code graph — local workspace
        </p>
      </div>

      <div className="w-full max-w-md space-y-3 rounded-xl border border-studio-line bg-studio-panel/80 p-5 shadow-xl backdrop-blur">
        <label className="block text-[10px] font-medium uppercase text-studio-muted">
          Project path
        </label>
        <input
          className="w-full rounded-md border border-studio-line bg-black/40 px-3 py-2 font-mono text-sm text-slate-100 outline-none focus:border-studio-accent"
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
            className="rounded-md border border-sky-600/60 bg-sky-600/25 px-4 py-2 text-sm text-white hover:bg-sky-500/30 disabled:cursor-not-allowed disabled:opacity-40"
          >
            Open folder
          </button>
          <button
            type="button"
            disabled={busy || !path.trim()}
            onClick={() => onOpenPath(path.trim())}
            className="rounded-md border border-studio-line bg-white/5 px-4 py-2 text-sm text-slate-200 hover:bg-white/10 disabled:cursor-not-allowed disabled:opacity-40"
          >
            New project
          </button>
        </div>
        {hint && <p className="text-xs text-amber-500/90">{hint}</p>}

        {recent.length > 0 && (
          <div className="border-t border-studio-line pt-3">
            <div className="mb-1 text-[10px] font-medium uppercase text-studio-muted">
              Recent
            </div>
            <ul className="max-h-40 space-y-1 overflow-y-auto text-left">
              {recent.map((r) => (
                <li key={r.path}>
                  <button
                    type="button"
                    className="w-full truncate rounded px-1 py-0.5 text-left font-mono text-xs text-sky-300/90 hover:bg-white/5"
                    onClick={() => onOpenPath(r.path)}
                    disabled={busy}
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
