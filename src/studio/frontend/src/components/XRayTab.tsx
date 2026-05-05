import { useEffect, useMemo, useState } from "react";
import type { BugFinding, BugScanSummary } from "@/lib/api";
import type { GraphEdge, GraphNode } from "@/types/drilldown";
import { detectXRayIssues } from "@/lib/xray_diagnostics";
import type { ScopeRecord } from "@/store/scopeRegistry";
import { useScope } from "@/store/studioScopeStore";
import { XRayContent } from "./XRayContent";
import { XRayHead } from "./XRayHead";
import type { XRayInnerTab } from "./XRayItabs";
import { XRayItabs } from "./XRayItabs";
import { XRayMetrics } from "./XRayMetrics";

type Stats = {
  files: number;
  functions: number;
  classes: number;
  edges: number;
  dark_matter: number;
  entangled: number;
};

type Props = {
  workspaceId: string;
  /** Scope id from studioScopeStore — echoed on Diagnostics for slice 17c tests. */
  scopeAtomId: string;
  graphNodes: Map<string, GraphNode>;
  graphEdges: GraphEdge[];
  stats: Stats;
  scopeById: Map<string, ScopeRecord>;
  projectPath: string;
  bugsScanFindings: BugFinding[];
  bugsScanSummary: BugScanSummary | null;
  onSuggestedAction: () => void;
};

type ConnectionRow = {
  direction: "out" | "in";
  name: string;
  path: string;
  type: string;
};

type XRayModel = {
  files: Array<{ name: string; path: string; connections: number }>;
  scopedNodes: GraphNode[];
  scopedEdges: GraphEdge[];
  connections: ConnectionRow[];
  incoming: number;
  outgoing: number;
  dark: number;
  entangled: number;
  issues: ReturnType<typeof detectXRayIssues>;
};

function basename(path: string) {
  return path.replace(/\\/g, "/").split("/").pop() || path || "(root)";
}

function dirname(path: string) {
  const s = path.replace(/\\/g, "/");
  const i = s.lastIndexOf("/");
  return i > 0 ? s.slice(0, i) : "";
}

function isSymbol(node: GraphNode) {
  return ["function", "method", "class"].includes(node.type);
}

function isDirectoryLike(node: GraphNode) {
  return ["directory", "module", "folder"].includes(node.type);
}

function relationLabel(edge: GraphEdge) {
  if (edge.relationship === "DARK_FORCE") return "DARK";
  return edge.relationship || "CALLS";
}

function edgeTouches(edge: GraphEdge, ids: Set<string>) {
  return ids.has(edge.source_id) || ids.has(edge.target_id);
}

function buildModel(
  selectedNode: GraphNode | null,
  nodes: GraphNode[],
  edges: GraphEdge[],
  _stats: Stats
): XRayModel {
  const scopePath = selectedNode?.file_path
    ? isDirectoryLike(selectedNode)
      ? selectedNode.file_path
      : dirname(selectedNode.file_path)
    : "";
  const scopedNodes = selectedNode
    ? isSymbol(selectedNode)
      ? [selectedNode]
      : nodes.filter((node) => (node.file_path ?? "").startsWith(scopePath))
    : nodes;
  const scopedIds = new Set(scopedNodes.map((node) => node.id));
  const scopedEdges = selectedNode
    ? edges.filter((edge) =>
        isSymbol(selectedNode)
          ? edge.source_id === selectedNode.id || edge.target_id === selectedNode.id
          : edgeTouches(edge, scopedIds)
      )
    : edges;
  let incoming = 0;
  let outgoing = 0;
  let dark = 0;
  let entangled = 0;
  const connections: ConnectionRow[] = [];
  const nodesById = new Map(nodes.map((node) => [node.id, node]));
  const fileConnections = new Map<string, number>();

  for (const edge of scopedEdges) {
    const sourceIn = scopedIds.has(edge.source_id);
    const targetIn = scopedIds.has(edge.target_id);
    const label = relationLabel(edge);
    if (label === "DARK") dark++;
    if (label === "ENTANGLED") entangled++;
    if (sourceIn && !targetIn) outgoing++;
    if (!sourceIn && targetIn) incoming++;

    const otherId = sourceIn ? edge.target_id : edge.source_id;
    const other = nodesById.get(otherId);
    connections.push({
      direction: sourceIn ? "out" : "in",
      name: other?.name ?? otherId,
      path: other?.file_path ?? "",
      type: label,
    });

    for (const id of [edge.source_id, edge.target_id]) {
      const node = nodesById.get(id);
      if (node?.file_path) {
        fileConnections.set(node.file_path, (fileConnections.get(node.file_path) ?? 0) + 1);
      }
    }
  }

  const files = Array.from(
    new Map(
      scopedNodes
        .filter((node) => node.file_path)
        .map((node) => [
          node.file_path as string,
          {
            name: basename(node.file_path as string),
            path: node.file_path as string,
            connections: fileConnections.get(node.file_path as string) ?? 0,
          },
        ])
    ).values()
  ).sort((a, b) => b.connections - a.connections || a.name.localeCompare(b.name));

  const issues = detectXRayIssues({
    scopedNodes,
    scopedEdges,
    incoming,
    outgoing,
    entangledCount: entangled,
    darkCount: dark,
  });

  return {
    files,
    scopedNodes,
    scopedEdges,
    connections: connections.slice(0, 18),
    incoming,
    outgoing,
    dark,
    entangled: selectedNode ? entangled : _stats.entangled,
    issues,
  };
}

function resolveHeader(
  selectedNode: GraphNode | null,
  scopeRecord: ScopeRecord | null,
  projectPath: string
): { badge: string; name: string; pathLine: string } {
  if (selectedNode && isSymbol(selectedNode)) {
    const badge =
      selectedNode.type === "method" ? "FUNCTION" : selectedNode.type.toUpperCase();
    return {
      badge,
      name: selectedNode.name,
      pathLine: `${selectedNode.file_path}:${selectedNode.line_start}`,
    };
  }
  if (selectedNode?.type === "file") {
    return {
      badge: "FILE",
      name: selectedNode.name || basename(selectedNode.file_path ?? ""),
      pathLine: selectedNode.file_path ?? "",
    };
  }
  if (selectedNode && isDirectoryLike(selectedNode)) {
    return {
      badge: "MODULE",
      name: selectedNode.name,
      pathLine: selectedNode.file_path ?? "",
    };
  }
  if (scopeRecord && scopeRecord.id !== "repo") {
    return {
      badge: scopeRecord.badge,
      name: scopeRecord.label,
      pathLine: scopeRecord.pathPrefix ?? "",
    };
  }
  return {
    badge: "REPO",
    name: "Workspace",
    pathLine: projectPath,
  };
}

export function XRayTab({
  workspaceId,
  scopeAtomId,
  graphNodes,
  graphEdges,
  stats,
  scopeById,
  projectPath,
  bugsScanFindings,
  bugsScanSummary,
  onSuggestedAction,
}: Props) {
  const { currentScope, selectedNodeId } = useScope();
  const [innerTab, setInnerTab] = useState<XRayInnerTab>("code");

  const scopeRecord = scopeById.get(currentScope) ?? null;

  useEffect(() => {
    const pathEcho =
      scopeRecord?.pathPrefix?.replace(/\\/g, "/") ||
      (currentScope === "repo" ? projectPath : currentScope);
    console.debug("[slice17c1] xray-head got scope", { path: pathEcho });
  }, [currentScope, projectPath, scopeRecord?.pathPrefix]);
  const selectedNode = selectedNodeId
    ? graphNodes.get(selectedNodeId) ?? null
    : null;

  const nodes = useMemo(() => Array.from(graphNodes.values()), [graphNodes]);

  const modelNodes = useMemo(() => {
    if (selectedNode) return nodes;
    const pre = scopeRecord?.pathPrefix?.replace(/\\/g, "/") ?? "";
    if (!pre) return nodes;
    return nodes.filter((n) => {
      const fp = (n.file_path ?? "").replace(/\\/g, "/");
      return fp === pre || fp.startsWith(`${pre}/`);
    });
  }, [nodes, scopeRecord?.pathPrefix, selectedNode]);

  const model = useMemo(
    () => buildModel(selectedNode, modelNodes, graphEdges, stats),
    [graphEdges, modelNodes, selectedNode, stats]
  );

  const header = resolveHeader(selectedNode, scopeRecord, projectPath);

  const scopeModel = useMemo(
    () => ({
      connections: model.connections,
      incoming: model.incoming,
      outgoing: model.outgoing,
      dark: model.dark,
    }),
    [model.connections, model.dark, model.incoming, model.outgoing]
  );

  const filesystemHygieneCleanLine = useMemo(() => {
    if (!bugsScanSummary) return null;
    const node = selectedNode;
    if (!node?.file_path) return null;
    if (
      !["function", "method", "class", "file"].includes(node.type)
    ) {
      return null;
    }
    const fp = node.file_path.replace(/\\/g, "/");
    const filthy = bugsScanFindings.some(
      (f) =>
        f.dimension === "filesystem_hygiene" &&
        (f.file ?? "").replace(/\\/g, "/") === fp
    );
    if (filthy) return null;
    return "✓ filesystem clean";
  }, [bugsScanFindings, bugsScanSummary, selectedNode]);

  return (
    <div className="xray-tab flex min-h-0 flex-1 flex-col gap-1 overflow-hidden">
      <XRayHead badge={header.badge} name={header.name} pathLine={header.pathLine} />
      <XRayItabs active={innerTab} onSelect={setInnerTab} />
      <div className="min-h-0 flex-1 overflow-y-auto pr-1">
        <XRayContent
          active={innerTab}
          workspaceId={workspaceId}
          scopeAtomId={scopeAtomId}
          selectedNode={selectedNode}
          scopeModel={scopeModel}
          issues={model.issues}
          filesystemHygieneCleanLine={filesystemHygieneCleanLine}
          onSuggestedAction={onSuggestedAction}
        />
      </div>
      <XRayMetrics scopedNodes={model.scopedNodes} scopedEdges={model.scopedEdges} />
    </div>
  );
}
