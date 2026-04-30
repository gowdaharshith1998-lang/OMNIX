import { recordFromGraphPayload } from "@/lib/graphNode";
import type { GraphEdge, GraphNode } from "@/types/drilldown";
import {
  CANONICAL_SCOPES,
  computeScopedStats,
  extendRegistryWithGraphNodes,
  scopeRecordsToMaps,
} from "@/store/scopeRegistry";

import graphPayload from "../../../../../web/graph_data_axiom_v2.json";

function countNodesUnderPrefix(nodes: GraphNode[], prefix: string | null): number {
  if (!prefix) return nodes.length;
  const pre = prefix.replace(/\\/g, "/");
  return nodes.filter((n) => {
    const fp = (n.file_path ?? "").replace(/\\/g, "/");
    return fp === pre || fp.startsWith(`${pre}/`);
  }).length;
}

export function loadAxiomFixture(): {
  nodes: GraphNode[];
  edges: GraphEdge[];
  repoGalaxyDirCount: number;
  repoScopedNodeCount: number;
  av2ScopedNodeCount: number;
  cryptoScopedNodeCount: number;
  pkgScopedNodeCount: number;
  statsAv2: ReturnType<typeof computeScopedStats>;
  statsCrypto: ReturnType<typeof computeScopedStats>;
  statsPkg: ReturnType<typeof computeScopedStats>;
  statsRepo: ReturnType<typeof computeScopedStats>;
  scopeByIdAv2: Map<string, (typeof CANONICAL_SCOPES)[number]>;
} {
  const raw = graphPayload as { nodes: Record<string, unknown>[]; links: Record<string, unknown>[] };
  const nodes: GraphNode[] = [];
  for (const n of raw.nodes) {
    const rec = recordFromGraphPayload(n);
    if (rec) nodes.push(rec);
  }
  const edges: GraphEdge[] = [];
  for (let i = 0; i < raw.links.length; i++) {
    const link = raw.links[i]!;
    const source = typeof link.source === "string" ? link.source : null;
    const target = typeof link.target === "string" ? link.target : null;
    if (!source || !target) continue;
    edges.push({
      id: typeof link.id === "string" || typeof link.id === "number" ? link.id : i,
      source_id: source,
      target_id: target,
      relationship: typeof link.type === "string" ? link.type : "CALLS",
    });
  }

  const seenDirs = new Set<string>();
  for (const n of nodes) {
    const fp = n.file_path?.replace(/\\/g, "/") ?? "";
    const parts = fp.split("/").filter(Boolean);
    if (parts.length >= 2) seenDirs.add(parts.slice(0, 2).join("/"));
  }
  const repoGalaxyDirCount = seenDirs.size;

  const axiomPrefix = "apps/backend/src/axiom";
  const cryptoPrefix = "apps/backend/src/axiom/services/crypto";
  const pkgPrefix = "packages/axiom-sdk";

  const statsAv2 = computeScopedStats(nodes, edges, axiomPrefix);
  const statsCrypto = computeScopedStats(nodes, edges, cryptoPrefix);
  const statsPkg = computeScopedStats(nodes, edges, pkgPrefix);
  const statsRepo = computeScopedStats(nodes, edges, null);

  const repoScopedNodeCount = nodes.length;
  const av2ScopedNodeCount = countNodesUnderPrefix(nodes, axiomPrefix);
  const cryptoScopedNodeCount = countNodesUnderPrefix(nodes, cryptoPrefix);
  const pkgScopedNodeCount = countNodesUnderPrefix(nodes, pkgPrefix);

  const extended = extendRegistryWithGraphNodes(CANONICAL_SCOPES, nodes);
  const { byId } = scopeRecordsToMaps(extended);

  return {
    nodes,
    edges,
    repoGalaxyDirCount,
    repoScopedNodeCount,
    av2ScopedNodeCount,
    cryptoScopedNodeCount,
    pkgScopedNodeCount,
    statsAv2,
    statsCrypto,
    statsPkg,
    statsRepo,
    scopeByIdAv2: byId,
  };
}
