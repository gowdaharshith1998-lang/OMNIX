import type { GraphEdge, GraphNode } from "@/types/drilldown";

export type XRayIssue = {
  severity: "high" | "med" | "low";
  icon: string;
  title: string;
  detail: string;
  action: string;
};

const order: Record<XRayIssue["severity"], number> = {
  high: 0,
  med: 1,
  low: 2,
};

export function detectXRayIssues(input: {
  scopedNodes: GraphNode[];
  scopedEdges: GraphEdge[];
  incoming: number;
  outgoing: number;
  entangledCount: number;
  darkCount: number;
}): XRayIssue[] {
  const issues: XRayIssue[] = [];
  const symbolCount = input.scopedNodes.filter((node) =>
    ["function", "method", "class"].includes(node.type)
  ).length;
  const byFile = new Map<string, number>();
  for (const node of input.scopedNodes) {
    if (!node.file_path) continue;
    byFile.set(node.file_path, (byFile.get(node.file_path) ?? 0) + 1);
  }
  const godFile = Array.from(byFile.entries()).sort((a, b) => b[1] - a[1])[0];

  if (input.entangledCount > 8) {
    issues.push({
      severity: "high",
      icon: "!",
      title: `${input.entangledCount} entangled pairs - extreme coupling`,
      detail: "Changing this scope risks breaking many dependents.",
      action: "Introduce API contracts/interfaces to decouple",
    });
  } else if (input.entangledCount > 4) {
    issues.push({
      severity: "med",
      icon: "!",
      title: `${input.entangledCount} entangled pairs - moderate coupling`,
      detail: "Tight coupling crosses scope boundaries.",
      action: "Invert dependencies around the highest-risk pairs",
    });
  }

  if (input.darkCount > 3) {
    issues.push({
      severity: "med",
      icon: "!",
      title: `${input.darkCount} dark matter dependencies`,
      detail: "Hidden env/config dependencies can fail silently.",
      action: "Add startup validation for required runtime state",
    });
  }

  if (godFile && godFile[1] > 100) {
    issues.push({
      severity: "high",
      icon: "!",
      title: `God file: ${basename(godFile[0])} (${godFile[1]} symbols)`,
      detail: "Too many responsibilities are concentrated in one file.",
      action: "Split by domain responsibility",
    });
  }

  if (symbolCount > 300) {
    issues.push({
      severity: "med",
      icon: "!",
      title: `High complexity: ${symbolCount} symbols`,
      detail: "This scope is large enough to slow review and testing.",
      action: "Extract sub-modules by feature",
    });
  }

  if (input.incoming > 20) {
    issues.push({
      severity: "med",
      icon: "!",
      title: `High fan-in: ${input.incoming} incoming dependencies`,
      detail: "Many modules depend on this scope; changes have wide blast radius.",
      action: "Use versioned interfaces before changing behavior",
    });
  }

  if (input.outgoing > 15) {
    issues.push({
      severity: "med",
      icon: "!",
      title: `High fan-out: ${input.outgoing} outgoing calls`,
      detail: "This scope depends on many others and is fragile to external changes.",
      action: "Introduce a facade or mediator",
    });
  }

  if (input.incoming === 0 && input.outgoing === 0 && input.scopedNodes.length > 0) {
    issues.push({
      severity: "low",
      icon: "i",
      title: "Orphan module - no external connections",
      detail: "This scope is isolated; it may be dead code or missing imports.",
      action: "Verify usage or remove if dead",
    });
  }

  return issues.sort((a, b) => order[a.severity] - order[b.severity]);
}

function basename(path: string) {
  return path.replace(/\\/g, "/").split("/").pop() || path;
}
