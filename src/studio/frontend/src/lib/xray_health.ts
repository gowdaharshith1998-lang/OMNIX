import type { GraphEdge, GraphNode } from "@/types/drilldown";

export type XRayHealth = {
  complexity: number;
  connectivity: number;
  entanglementRisk: number;
};

function clampPercent(value: number) {
  return Math.max(0, Math.min(100, Math.round(value)));
}

export function computeXRayHealth(input: {
  scopedNodes: GraphNode[];
  scopedEdges: GraphEdge[];
  entangledCount: number;
}): XRayHealth {
  const symbolCount = input.scopedNodes.filter((node) =>
    ["function", "method", "class"].includes(node.type)
  ).length;
  return {
    complexity: clampPercent((symbolCount / 300) * 100),
    connectivity: clampPercent((input.scopedEdges.length / 100) * 100),
    entanglementRisk: clampPercent(input.entangledCount * 10),
  };
}
