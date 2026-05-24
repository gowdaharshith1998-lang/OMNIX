import { useCallback, useEffect, useRef, useState } from "react";
import { getStudioInitial, openWorkspace } from "@/lib/api";
import { Welcome } from "./components/Welcome";
import { Workspace } from "./components/Workspace";
import { M42Workspace } from "./components/m42/M42Workspace";

const USE_M42 =
  typeof window === "undefined"
    ? true
    : new URLSearchParams(window.location.search).get("legacy") !== "1";

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

  const initialOpenAttemptedRef = useRef(false);

  const onOpenPath = useCallback((path: string) => {
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
  }, []);

  useEffect(() => {
    if (initialOpenAttemptedRef.current) return;
    initialOpenAttemptedRef.current = true;
    let cancelled = false;
    void getStudioInitial()
      .then((initial) => {
        const path = initial.path?.trim();
        if (!cancelled && path) onOpenPath(path);
      })
      .catch(() => {
        // No initial path means the welcome screen remains the manual fallback.
      });
    return () => {
      cancelled = true;
    };
  }, [onOpenPath]);

  if (session) {
    if (USE_M42) {
      return (
        <M42Workspace
          workspaceId={session.workspaceId}
          projectPath={session.path}
          initialStats={session.stats}
          onBack={() => setSession(null)}
        />
      );
    }
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
