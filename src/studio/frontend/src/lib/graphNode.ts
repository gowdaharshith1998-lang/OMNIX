import type { GraphNode } from "@/types/drilldown";

type ChangeEntry = { old?: unknown; new?: unknown } | undefined;

/**
 * Merges server node_modified delta (uses start_line in changes) with client graph shape (line_start).
 */
export function applyNodeModified(
  n: GraphNode,
  changes: Record<string, ChangeEntry> | undefined
): GraphNode {
  if (!changes) return n;
  let o: GraphNode = { ...n };
  for (const [k, v] of Object.entries(changes)) {
    if (!v || typeof v !== "object" || !("new" in v)) continue;
    const nv = (v as { new: unknown }).new;
    if (k === "start_line") o = { ...o, line_start: Number(nv) };
    else if (k === "end_line") o = { ...o, line_end: Number(nv) };
    else if (k === "file_path") o = { ...o, file_path: nv == null ? null : String(nv) };
    else if (k === "name") o = { ...o, name: String(nv) };
    else if (k === "type") o = { ...o, type: String(nv) };
  }
  return o;
}
