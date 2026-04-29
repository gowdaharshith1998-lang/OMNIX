import { useMemo } from "react";
import type { GraphEdge, GraphNode } from "@/types/drilldown";
import { detectXRayIssues, type XRayIssue } from "@/lib/xray_diagnostics";
import { computeXRayHealth, type XRayHealth } from "@/lib/xray_health";

type Stats = {
  files: number;
  functions: number;
  classes: number;
  edges: number;
  dark_matter: number;
  entangled: number;
};

type Props = {
  selectedNode: GraphNode | null;
  graphNodes: Map<string, GraphNode>;
  graphEdges: GraphEdge[];
  stats: Stats;
  onSuggestedAction: () => void;
};

type ConnectionRow = {
  direction: "out" | "in";
  name: string;
  path: string;
  type: string;
};

type XRayModel = {
  title: string;
  subtitle: string;
  files: Array<{ name: string; path: string; connections: number }>;
  scopedNodes: GraphNode[];
  scopedEdges: GraphEdge[];
  connections: ConnectionRow[];
  incoming: number;
  outgoing: number;
  dark: number;
  entangled: number;
  health: XRayHealth;
  issues: XRayIssue[];
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
  stats: Stats
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
    title: selectedNode ? selectedNode.name : "Repository",
    subtitle: selectedNode?.file_path ?? "Whole graph intelligence",
    files,
    scopedNodes,
    scopedEdges,
    connections: connections.slice(0, 18),
    incoming,
    outgoing,
    dark,
    entangled: selectedNode ? entangled : stats.entangled,
    health: computeXRayHealth({ scopedNodes, scopedEdges, entangledCount: entangled }),
    issues,
  };
}

function StatTile({ label, value, tone }: { label: string; value: number; tone: string }) {
  return (
    <div className={`xray-stat ${tone}`}>
      <div>{value}</div>
      <span>{label}</span>
    </div>
  );
}

function HealthBar({ label, value }: { label: string; value: number }) {
  return (
    <div className="xray-health-row">
      <div>
        <span>{label}</span>
        <b>{value}%</b>
      </div>
      <div className="xray-health-track">
        <i style={{ width: `${value}%` }} />
      </div>
    </div>
  );
}

function Issues({
  issues,
  onSuggestedAction,
}: {
  issues: XRayIssue[];
  onSuggestedAction: () => void;
}) {
  if (issues.length === 0) {
    return (
      <section className="xray-section">
        <h3>DIAGNOSTICS</h3>
        <div className="xray-ok">No issues detected - this scope looks healthy.</div>
      </section>
    );
  }
  return (
    <section className="xray-section">
      <h3>DIAGNOSTICS ({issues.length} issues)</h3>
      <div className="xray-issues">
        {issues.map((issue) => (
          <article key={`${issue.title}:${issue.action}`} className={`xray-issue ${issue.severity}`}>
            <strong>{issue.icon} {issue.title}</strong>
            <p>{issue.detail}</p>
            <button type="button" onClick={onSuggestedAction}>
              {issue.action}
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}

function AiAgentZone() {
  return (
    <section className="xray-section xray-ai-zone">
      <h3>AI AGENT</h3>
      <div className="xray-ai-unavailable">
        AI Agent unavailable - set OMNIX_AI_KEY or install Ollama.
      </div>
    </section>
  );
}

export function XRayTab({
  selectedNode,
  graphNodes,
  graphEdges,
  stats,
  onSuggestedAction,
}: Props) {
  const nodes = useMemo(() => Array.from(graphNodes.values()), [graphNodes]);
  const model = useMemo(
    () => buildModel(selectedNode, nodes, graphEdges, stats),
    [graphEdges, nodes, selectedNode, stats]
  );
  const branch = !selectedNode
    ? "repo"
    : isSymbol(selectedNode)
      ? "symbol"
      : "module";

  switch (branch) {
    case "symbol":
      return (
        <XRayShell model={model} eyebrow={selectedNode?.type.toUpperCase() ?? "SYMBOL"}>
          <section className="xray-section">
            <h3>SIGNATURE</h3>
            <div className="xray-signature">
              {selectedNode?.name}
              <span>{selectedNode?.file_path}:{selectedNode?.line_start}</span>
            </div>
          </section>
          <Connections model={model} />
          <Issues issues={model.issues} onSuggestedAction={onSuggestedAction} />
          <Health model={model} />
          <AiAgentZone />
        </XRayShell>
      );
    case "module":
      return (
        <XRayShell model={model} eyebrow="MODULE">
          <Tiles model={model} />
          <Files model={model} />
          <Connections model={model} />
          <Issues issues={model.issues} onSuggestedAction={onSuggestedAction} />
          <Health model={model} />
          <AiAgentZone />
        </XRayShell>
      );
    case "repo":
    default:
      return (
        <XRayShell model={model} eyebrow="REPO">
          <Tiles model={model} repoStats={stats} />
          <Issues issues={model.issues} onSuggestedAction={onSuggestedAction} />
          <Health model={model} />
          <AiAgentZone />
        </XRayShell>
      );
  }
}

function XRayShell({
  model,
  eyebrow,
  children,
}: {
  model: XRayModel;
  eyebrow: string;
  children: React.ReactNode;
}) {
  return (
    <div className="xray-tab">
      <header className="xray-header">
        <div className="xray-label">X-RAY</div>
        <div className="xray-eyebrow">{eyebrow}</div>
        <h2>{model.title}</h2>
        <p>{model.subtitle}</p>
      </header>
      {children}
    </div>
  );
}

function Tiles({ model, repoStats }: { model: XRayModel; repoStats?: Stats }) {
  const fileCount = repoStats?.files ?? model.files.length;
  const functionCount =
    repoStats?.functions ?? model.scopedNodes.filter((node) => isSymbol(node)).length;
  const connectionCount = repoStats?.edges ?? model.scopedEdges.length;
  return (
    <section className="xray-tiles">
      <StatTile label="Files" value={fileCount} tone="purple" />
      <StatTile label="Functions" value={functionCount} tone="teal" />
      <StatTile label="Connections" value={connectionCount} tone="amber" />
    </section>
  );
}

function Files({ model }: { model: XRayModel }) {
  return (
    <section className="xray-section">
      <h3>FILES (by connections)</h3>
      <div className="xray-list">
        {model.files.slice(0, 12).map((file) => (
          <div key={file.path} className="xray-file-row">
            <span>{file.name}</span>
            <b>+{file.connections}</b>
          </div>
        ))}
        {model.files.length === 0 && <div className="xray-empty">No files in scope.</div>}
      </div>
    </section>
  );
}

function Connections({ model }: { model: XRayModel }) {
  return (
    <section className="xray-section">
      <h3>CONNECTIONS</h3>
      <div className="xray-connection-summary">
        {model.outgoing} outgoing · {model.incoming} incoming · {model.dark} dark
      </div>
      <div className="xray-list">
        {model.connections.map((conn, idx) => (
          <div key={`${conn.name}:${conn.type}:${idx}`} className="xray-connection-row">
            <span>{conn.direction === "out" ? "->" : "<-"} {conn.name}</span>
            <b className={`rel-${conn.type.toLowerCase()}`}>{conn.type}</b>
          </div>
        ))}
        {model.connections.length === 0 && <div className="xray-empty">No external connections.</div>}
      </div>
    </section>
  );
}

function Health({ model }: { model: XRayModel }) {
  return (
    <section className="xray-section">
      <h3>HEALTH</h3>
      <HealthBar label="Complexity" value={model.health.complexity} />
      <HealthBar label="Connectivity" value={model.health.connectivity} />
      <HealthBar label="Entanglement risk" value={model.health.entanglementRisk} />
    </section>
  );
}
