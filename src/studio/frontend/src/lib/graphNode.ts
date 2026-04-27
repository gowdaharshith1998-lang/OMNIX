import type { GraphNode } from "@/types/drilldown";

type ChangeEntry = { old?: unknown; new?: unknown } | undefined;

function basenamePath(p: string): string {
  const s = p.replace(/\\/g, "/");
  const i = s.lastIndexOf("/");
  return i >= 0 ? s.slice(i + 1) : s;
}

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
 * Map a server `node` to the T1-bundled viewer shape: `id`, `name`, `type`, `file`, `line`,
 * `val`, `color` (+ `line_start`, `line_end`, `metadata` with `ws_id` for delta lookup).
 */
export function wsNodeToViewerShape(
  node: Record<string, unknown>
): Record<string, unknown> {
  const originalId = node.id;
  const t = typeof node.type === "string" ? node.type : "";
  const filePath = typeof node.file_path === "string" ? node.file_path : "";
  let name = typeof node.name === "string" ? node.name : "";
  const lineStart =
    typeof node.line_start === "number" ? node.line_start : 0;
  const lineEnd =
    typeof node.line_end === "number" ? node.line_end : 0;

  const metaBase =
    node.metadata != null &&
    typeof node.metadata === "object" &&
    !Array.isArray(node.metadata)
      ? { ...(node.metadata as Record<string, unknown>) }
      : {};

  const attachMeta = (out: Record<string, unknown>) => {
    const m = { ...metaBase };
    if (originalId != null) {
      m.ws_id = originalId;
      m.original_id = originalId;
    }
    out.metadata = m;
  };

  const preserveLines = (out: Record<string, unknown>) => {
    out.line_start = lineStart;
    out.line_end = lineEnd;
  };

  if (t === "file" || t === "directory" || t === "folder") {
    const id = filePath || (typeof originalId === "string" ? originalId : "");
    const displayName =
      name || (id ? basenamePath(id) : "") || String(originalId ?? "");
    const color = t === "file" ? "#3b82f6" : "#a78bfa";
    const out: Record<string, unknown> = {
      id,
      name: displayName,
      type: t,
      file: filePath,
      line: 1,
      val: 99,
      color,
    };
    preserveLines(out);
    attachMeta(out);
    return out;
  }

  if (t === "function" || t === "method" || t === "class") {
    const synthesizedId =
      filePath && name ? `${filePath}::${name}` : typeof originalId === "string"
        ? originalId
        : "";
    const line = lineStart;
    let val = 2;
    let color = "#4ade80";
    if (t === "method") {
      color = "#fbbf24";
      val = 2;
    } else if (t === "class") {
      val = 3;
      color = "#a855f7";
    }
    const out: Record<string, unknown> = {
      id: synthesizedId,
      name,
      type: t,
      file: filePath,
      line,
      val,
      color,
    };
    preserveLines(out);
    attachMeta(out);
    return out;
  }

  const out: Record<string, unknown> = {
    id:
      typeof originalId === "string"
        ? originalId
        : String(originalId ?? ""),
    name,
    type: typeof node.type === "string" ? node.type : t || "unknown",
    file: filePath,
    line: lineStart,
    val: 1,
    color: "#94a3b8",
  };
  preserveLines(out);
  attachMeta(out);
  return out;
}

/** Map WebSocket `edge` dict (source_id, target_id, relationship) to `links` entry. */
export function wsEdgeToLinkShape(
  edge: Record<string, unknown>
): Record<string, unknown> {
  return {
    id: edge.id,
    source: edge.source_id,
    target: edge.target_id,
    type:
      typeof edge.relationship === "string" ? edge.relationship : "CALLS",
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
    else if (k === "file_path")
      o = { ...o, file_path: nv == null ? null : String(nv) };
    else if (k === "name") o = { ...o, name: String(nv) };
    else if (k === "type") o = { ...o, type: String(nv) };
  }
  return o;
}
