import type { GraphNode } from "@/types/drilldown";

type ChangeEntry = { old?: unknown; new?: unknown } | undefined;

/**
 * WebSocket and analyze `graph_data.json` shapes:
 * - server: `file_path`, `line_start`, `line_end`
 * - static graph: `file`, `line` (and optional `line_start` / `line_end` if present)
 */
export function recordFromGraphPayload(
  n: Record<string, unknown>
): GraphNode | null {
  if (
    typeof n.id !== "string" ||
    typeof n.name !== "string" ||
    typeof n.type !== "string"
  ) {
    return null;
  }
  const filePath =
    typeof n.file_path === "string"
      ? n.file_path
      : typeof n.file === "string"
        ? n.file
        : null;
  let lineStart = 0;
  let lineEnd = 0;
  if (typeof n.line_start === "number") lineStart = n.line_start;
  else if (typeof n.line === "number") lineStart = n.line;
  if (typeof n.line_end === "number") lineEnd = n.line_end;
  else if (lineStart > 0) lineEnd = lineStart;
  return {
    id: n.id,
    name: n.name,
    type: n.type,
    file_path: filePath,
    line_start: lineStart,
    line_end: lineEnd,
  };
}

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
