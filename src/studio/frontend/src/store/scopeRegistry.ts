import type { GraphNode } from "@/types/drilldown";

export type ScopeRecord = {
  id: string;
  parentId: string | null;
  /** UI title (breadcrumb, X-Ray header) */
  label: string;
  /** X-Ray eyebrow when no symbol selected */
  badge: "REPO" | "MODULE" | "FILE";
  /** Directory prefix or file path for metrics filtering; null = whole repo */
  pathPrefix: string | null;
};

/** Canonical demo scopes used by T1 graph fixtures and slice-15 tests. */
export const CANONICAL_SCOPES: ScopeRecord[] = [
  {
    id: "repo",
    parentId: null,
    label: "Repository",
    badge: "REPO",
    pathPrefix: null,
  },
  {
    id: "av2",
    parentId: "repo",
    label: "AXIOM-V2",
    badge: "MODULE",
    pathPrefix: "apps/backend/src/axiom",
  },
  {
    id: "crypto",
    parentId: "av2",
    label: "crypto",
    badge: "MODULE",
    pathPrefix: "apps/backend/src/axiom/services/crypto",
  },
  {
    id: "hyb",
    parentId: "crypto",
    label: "hybrid_signer.py",
    badge: "FILE",
    pathPrefix: "apps/backend/src/axiom/services/crypto/hybrid_signer.py",
  },
];

export function scopeRecordsToMaps(records: ScopeRecord[]) {
  const byId = new Map<string, ScopeRecord>();
  const pathToId = new Map<string, string>();
  for (const r of records) {
    byId.set(r.id, r);
    if (r.pathPrefix != null) pathToId.set(r.pathPrefix, r.id);
  }
  return { byId, pathToId };
}

/** Longest matching pathPrefix wins (file path before parent dirs). */
export function resolveScopeIdForPath(
  pathToId: Map<string, string>,
  filePath: string | null | undefined,
  viewLevel: "galaxy" | "star" | "planet"
): string {
  const norm = (filePath ?? "").replace(/\\/g, "/");
  if (viewLevel === "galaxy" || !norm) return "repo";

  let best: { len: number; id: string } | null = null;
  for (const [prefix, scopeId] of pathToId) {
    if (!prefix) continue;
    if (norm === prefix || norm.startsWith(`${prefix}/`)) {
      if (!best || prefix.length > best.len) {
        best = { len: prefix.length, id: scopeId };
      }
    }
  }
  return best?.id ?? "repo";
}

/**
 * Merge canonical scopes with top-level directory prefixes from the live graph
 * so unknown workspaces still get navigable scope ids.
 */
export function extendRegistryWithGraphNodes(
  base: ScopeRecord[],
  nodes: Iterable<GraphNode>
): ScopeRecord[] {
  const byId = new Map(base.map((r) => [r.id, r] as const));
  const pathToId = new Map<string, string>();
  for (const r of base) {
    if (r.pathPrefix) pathToId.set(r.pathPrefix, r.id);
  }

  const seenDirs = new Set<string>();
  for (const n of nodes) {
    const fp = n.file_path?.replace(/\\/g, "/") ?? "";
    if (!fp) continue;
    const parts = fp.split("/").filter(Boolean);
    if (parts.length < 2) continue;
    /* Directory prefixes along the path (slice 17c); exclude filename segment when it looks like a file. */
    const last = parts[parts.length - 1] ?? "";
    const limit = last.includes(".") ? parts.length - 1 : parts.length;
    for (let len = 2; len <= limit; len++) {
      seenDirs.add(parts.slice(0, len).join("/"));
    }
  }

  let idx = 0;
  for (const dir of seenDirs) {
    if (pathToId.has(dir)) continue;
    const id = `dir_${idx++}`;
    const label = dir.includes("/") ? dir.split("/").pop() ?? dir : dir;
    const rec: ScopeRecord = {
      id,
      parentId: "repo",
      label,
      badge: "MODULE",
      pathPrefix: dir,
    };
    byId.set(id, rec);
    pathToId.set(dir, id);
  }

  return [...byId.values()];
}

export function ancestryChain(scopeId: string, byId: Map<string, ScopeRecord>): ScopeRecord[] {
  const out: ScopeRecord[] = [];
  let cur: string | null = scopeId;
  while (cur) {
    const r = byId.get(cur);
    if (!r) break;
    out.push(r);
    cur = r.parentId;
  }
  return out.reverse();
}

export function computeScopedStats(
  nodes: GraphNode[],
  edges: { source_id: string; target_id: string }[],
  pathPrefix: string | null
): {
  files: number;
  functions: number;
  classes: number;
  edges: number;
  dark_matter: number;
  entangled: number;
} {
  const inScope = (fp: string | null | undefined) => {
    const p = (fp ?? "").replace(/\\/g, "/");
    if (!pathPrefix) return true;
    const pre = pathPrefix.replace(/\\/g, "/");
    return p === pre || p.startsWith(pre + "/");
  };

  const scopedNodes = nodes.filter((n) => inScope(n.file_path));
  const idSet = new Set(scopedNodes.map((n) => n.id));
  const fileSet = new Set<string>();
  let functions = 0;
  let classes = 0;
  let dark_matter = 0;

  for (const n of scopedNodes) {
    if (n.type === "file" && n.file_path) fileSet.add(n.file_path);
    if (n.type === "function" || n.type === "method") functions += 1;
    if (n.type === "class") classes += 1;
    if (n.type === "dark_matter") dark_matter += 1;
  }

  let entangled = 0;
  const scopedEdges = edges.filter(
    (e) => idSet.has(e.source_id) && idSet.has(e.target_id)
  );
  for (const e of scopedEdges) {
    const rel = (e as { relationship?: string }).relationship;
    if (rel === "ENTANGLED") entangled += 1;
  }

  return {
    files: fileSet.size,
    functions,
    classes,
    edges: scopedEdges.length,
    dark_matter,
    entangled,
  };
}
