/** Shared ?t1=1 gate: bundled static graph (T1) vs live WebSocket path. */
export function isT1Mode(): boolean {
  if (import.meta.env.VITE_OMNIX_T1 === "1") return true;
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get("t1") === "1";
}
