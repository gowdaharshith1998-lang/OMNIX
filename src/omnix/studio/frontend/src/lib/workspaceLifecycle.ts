const jsonHeaders = { "Content-Type": "application/json" };

/** Best-effort server cleanup when leaving the workspace (ignore failures). */
export async function closeWorkspace(workspaceId: string): Promise<void> {
  try {
    await fetch("/api/workspace/close", {
      method: "POST",
      headers: jsonHeaders,
      body: JSON.stringify({ workspace_id: workspaceId }),
    });
  } catch {
    /* best effort */
  }
}

/** Register sendBeacon on tab unload; returns cleanup that removes the listener. */
export function registerBeaconUnload(workspaceId: string): () => void {
  const handler = () => {
    const blob = new Blob([JSON.stringify({ workspace_id: workspaceId })], {
      type: "application/json",
    });
    navigator.sendBeacon("/api/workspace/close", blob);
  };
  window.addEventListener("beforeunload", handler);
  return () => window.removeEventListener("beforeunload", handler);
}
