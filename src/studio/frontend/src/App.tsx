import { useState } from "react";
import { openWorkspace } from "@/lib/api";
import { Welcome } from "./components/Welcome";
import { Workspace } from "./components/Workspace";

export default function App() {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [session, setSession] = useState<{
    workspaceId: string;
    path: string;
    stats: {
      files: number;
      functions: number;
      classes: number;
      edges: number;
    };
  } | null>(null);

  const onOpenPath = (path: string) => {
    setErr(null);
    setBusy(true);
    void (async () => {
      try {
        const o = await openWorkspace(path);
        setSession({
          workspaceId: o.workspace_id,
          path,
          stats: o.stats,
        });
      } catch (e) {
        setErr(e instanceof Error ? e.message : "open failed");
      } finally {
        setBusy(false);
      }
    })();
  };

  if (session) {
    return (
      <Workspace
        workspaceId={session.workspaceId}
        projectPath={session.path}
        initialStats={session.stats}
        onBack={() => setSession(null)}
      />
    );
  }

  return (
    <div className="omnix-hex-bg min-h-full text-omnix-text-primary">
      {err && (
        <div className="bg-rose-900/50 px-3 py-1 text-center text-xs text-rose-200">
          {err}
        </div>
      )}
      <Welcome onOpenPath={onOpenPath} busy={busy} />
    </div>
  );
}
