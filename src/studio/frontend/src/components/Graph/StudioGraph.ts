// @ts-nocheck
import type { GraphEdge, GraphNode } from "@/types/drilldown";
import { isT1Mode } from "@/lib/t1Mode";
import {
  recordFromGraphPayload,
  wsEdgeToLinkShape,
  wsNodeToViewerShape,
} from "@/lib/graphNode";
import { installOmnixViewerEngine } from "./viewerEngine";

export type ViewerScopePayload =
  | { kind: "repo" }
  | { kind: "directory"; path: string }
  | { kind: "file"; path: string };

export type ScopeNavigationSpec = ViewerScopePayload;

export type StudioGraphOptions = {
  onFunctionNodeClick?: (nodeId: string) => void;
  onFileOrDirClick?: (filePath: string) => void;
  onDeselect?: () => void;
  onNavigationStateChange?: (canGoBack: boolean) => void;
  /** Slice 15 — constellation reports semantic scope for React shell (breadcrumb / X-Ray / stats). */
  onViewerScope?: (payload: ViewerScopePayload) => void;
  /** Same role as T1 `onT1GraphNodes`: DrillDown catalog after full graph snapshot. */
  onDrilldownCatalog?: (nodes: GraphNode[]) => void;
  /** X-Ray catalog after full graph snapshot. */
  onDrilldownEdges?: (edges: GraphEdge[]) => void;
};

type StudioHandle = {
  _container: HTMLElement;
  _options: StudioGraphOptions;
  _loadGraphFromData?: (data: unknown) => void;
  _applyScopeNavigation?: (spec: ScopeNavigationSpec) => void;
  _ingestDelta?: (message: unknown) => void;
  _destroy?: () => void;
  _flashNodeRim?: (
    nodeId: string,
    opts?: { color?: number; durationMs?: number }
  ) => void;
  _fadeAndRemoveNode?: (
    nodeId: string,
    opts?: { durationMs?: number }
  ) => void;
  /** T2 v2 slice 5 — live node_added “born” animation; returns true if a cell was created */
  _bornNode?: (
    wsId: string,
    nodeData: Record<string, unknown>,
    opts?: { durationMs?: number }
  ) => boolean;
  /** T2 v2 slice 6a — live edge_added; returns true if a CALLS link was added to planet force graph */
  _bornEdge?: (fromSynthId: string, toSynthId: string) => boolean;
  /** T2 v2 slice 6b — viewer reports whether planet PIXI layer is ready for live deltas */
  setViewContext?: (context: "planet-ready" | "non-planet") => void;
  _canGoBack?: () => boolean;
  _goBack?: () => void;
};

type BootstrapBuffer = {
  nodes: Record<string, unknown>[];
  edges: Record<string, unknown>[];
  started: boolean;
  completed: boolean;
  snapshotDone: boolean;
  lastStats: Record<string, unknown>;
};

/**
 * Class wrapper for the transplanted analyze viewer (see viewerEngine.ts).
 * Graphics code lives in viewerEngine; this only holds the host object for installOmnixViewerEngine.
 */
export class StudioGraph {
  private _studio: StudioHandle;

  private _wsIdToSynthId = new Map<string, string>();

  private _viewContext: "planet-ready" | "non-planet" = "non-planet";

  private _bootstrapBuffer: BootstrapBuffer = {
    nodes: [],
    edges: [],
    started: false,
    completed: false,
    snapshotDone: false,
    lastStats: {},
  };

  constructor(
    container: HTMLElement,
    options: StudioGraphOptions = {}
  ) {
    this._studio = { _container: container, _options: options };
    installOmnixViewerEngine(this._studio);
    this._studio.setViewContext = (context: "planet-ready" | "non-planet") => {
      // eslint-disable-next-line no-console
      console.debug("[t2-slice6b] viewContext →", context);
      this._viewContext = context;
    };
  }

  private _shouldDropLivePlanetDelta(): boolean {
    return (
      this._bootstrapBuffer.completed &&
      this._viewContext !== "planet-ready"
    );
  }

  setOptions(options: StudioGraphOptions) {
    this._studio._options = options;
  }

  loadInitial(
    nodes: unknown[],
    links: unknown[],
    stats?: Record<string, unknown>
  ) {
    this._studio._loadGraphFromData?.({
      nodes,
      links,
      stats: stats ?? {},
    });
  }

  canGoBack(): boolean {
    return Boolean(this._studio._canGoBack?.());
  }

  goBack(): void {
    this._studio._goBack?.();
  }

  applyScopeNavigation(spec: ScopeNavigationSpec): void {
    this._studio._applyScopeNavigation?.(spec);
  }

  private _logDispatch(m: Record<string, unknown>, t: string) {
    switch (t) {
      case "bootstrap_start":
      case "bootstrap_complete":
        // eslint-disable-next-line no-console
        console.debug("[t2-slice2]", t, "");
        break;
      case "node_added": {
        const node = m.node;
        const id =
          node &&
          typeof node === "object" &&
          (node as { id?: unknown }).id != null
            ? String((node as { id: unknown }).id)
            : "";
        // eslint-disable-next-line no-console
        console.debug("[t2-slice2]", t, id);
        break;
      }
      case "node_modified": {
        const id = m.node_id != null ? String(m.node_id) : "";
        // eslint-disable-next-line no-console
        console.debug("[t2-slice2]", t, id);
        break;
      }
      case "node_removed": {
        const id = m.node_id != null ? String(m.node_id) : "";
        // eslint-disable-next-line no-console
        console.debug("[t2-slice2]", t, id);
        break;
      }
      case "edge_added": {
        const e = m.edge;
        let br = "";
        if (e && typeof e === "object") {
          const o = e as Record<string, unknown>;
          if (o.id != null) br = String(o.id);
          else
            br = [o.from_id, o.to_id]
              .filter((x) => x != null)
              .map(String)
              .join("→");
        }
        // eslint-disable-next-line no-console
        console.debug("[t2-slice2]", t, br);
        break;
      }
      case "edge_removed": {
        const id = m.edge_id != null ? String(m.edge_id) : "";
        // eslint-disable-next-line no-console
        console.debug("[t2-slice2]", t, id);
        break;
      }
      case "stats": {
        const br = `files=${m.files ?? "?"}`;
        // eslint-disable-next-line no-console
        console.debug("[t2-slice2]", t, br);
        break;
      }
      case "error": {
        // eslint-disable-next-line no-console
        console.debug("[t2-slice2]", t, String(m.message ?? ""));
        break;
      }
      case "pong": {
        // eslint-disable-next-line no-console
        console.debug("[t2-slice2]", t, String(m.ts ?? ""));
        break;
      }
      default:
        // eslint-disable-next-line no-console
        console.debug("[t2-slice2] unknown", t || "(no type)");
    }
  }

  private _renderBufferedSnapshot(): void {
    const rawNodes = this._bootstrapBuffer.nodes.map(wsNodeToViewerShape);
    this._wsIdToSynthId = new Map<string, string>();
    for (let i = 0; i < rawNodes.length; i++) {
      const node = rawNodes[i] as Record<string, unknown>;
      const meta = node.metadata;
      if (
        meta &&
        typeof meta === "object" &&
        !Array.isArray(meta) &&
        typeof (meta as Record<string, unknown>).ws_id === "string" &&
        typeof node.id === "string"
      ) {
        const wsId = String((meta as Record<string, unknown>).ws_id);
        this._wsIdToSynthId.set(wsId, node.id as string);
      }
    }
    const rawLinks = this._bootstrapBuffer.edges.map(wsEdgeToLinkShape);
    const payload = {
      nodes: rawNodes,
      links: rawLinks,
      stats: this._bootstrapBuffer.lastStats,
    };
    this._studio._loadGraphFromData?.(payload);
    const cb = this._studio._options.onDrilldownCatalog;
    if (cb) {
      const list: GraphNode[] = [];
      for (let i = 0; i < rawNodes.length; i++) {
        const rec = recordFromGraphPayload(rawNodes[i] as Record<string, unknown>);
        if (rec) list.push(rec);
      }
      cb(list);
    }
    const edgeCb = this._studio._options.onDrilldownEdges;
    if (edgeCb) {
      const list: GraphEdge[] = [];
      for (let i = 0; i < rawLinks.length; i++) {
        const edge = rawLinks[i] as Record<string, unknown>;
        const source = typeof edge.source === "string" ? edge.source : null;
        const target = typeof edge.target === "string" ? edge.target : null;
        if (source && target) {
          list.push({
            id: typeof edge.id === "string" || typeof edge.id === "number" ? edge.id : i,
            source_id: source,
            target_id: target,
            relationship: typeof edge.type === "string" ? edge.type : "CALLS",
          });
        }
      }
      edgeCb(list);
    }
  }

  /** Day 11a T2+ — live WebSocket deltas; bootstrap buffers then one static rebuild. */
  ingestDelta(message: unknown) {
    if (isT1Mode()) {
      const m0 = message as Record<string, unknown>;
      const t0 = typeof m0.type === "string" ? m0.type : "";
      this._logDispatch(m0, t0);
      return;
    }

    const m = message as Record<string, unknown>;
    const t = typeof m.type === "string" ? m.type : "";
    const inBootstrap =
      this._bootstrapBuffer.started && !this._bootstrapBuffer.completed;

    switch (t) {
      case "bootstrap_start":
        this._bootstrapBuffer = {
          nodes: [],
          edges: [],
          started: true,
          completed: false,
          snapshotDone: false,
          lastStats: {},
        };
        // eslint-disable-next-line no-console
        console.debug("[t2-slice2] bootstrap_start");
        break;

      case "node_added": {
        if (inBootstrap && m.node && typeof m.node === "object") {
          this._bootstrapBuffer.nodes.push(m.node as Record<string, unknown>);
          break;
        }
        if (!this._bootstrapBuffer.completed) {
          // eslint-disable-next-line no-console
          console.debug(
            "[t2-slice5] node_added pre-bootstrap (live dropped)",
            m
          );
          break;
        }
        if (this._shouldDropLivePlanetDelta()) {
          // eslint-disable-next-line no-console
          console.debug(
            "[t2-slice6b] live delta dropped, viewContext=",
            this._viewContext,
            "verb=",
            t
          );
          return;
        }
        if (!m.node || typeof m.node !== "object") {
          // eslint-disable-next-line no-console
          console.debug("[t2-slice5] node_added missing node payload", m);
          break;
        }
        const raw = m.node as Record<string, unknown>;
        const viewerShape = wsNodeToViewerShape(raw);
        const meta = viewerShape.metadata;
        const wsId =
          meta &&
          typeof meta === "object" &&
          !Array.isArray(meta) &&
          typeof (meta as Record<string, unknown>).ws_id === "string"
            ? String((meta as Record<string, unknown>).ws_id)
            : typeof raw.id === "string"
              ? raw.id
              : null;
        if (!wsId) {
          // eslint-disable-next-line no-console
          console.debug("[t2-slice5] node_added missing ws id", m);
          break;
        }
        if (this._wsIdToSynthId.has(wsId)) {
          // eslint-disable-next-line no-console
          console.debug("[t2-slice5] duplicate node_added for", wsId);
          break;
        }
        const synthId =
          typeof viewerShape.id === "string" ? viewerShape.id : null;
        if (!synthId) {
          // eslint-disable-next-line no-console
          console.debug("[t2-slice5] node_added could not resolve synth id", m);
          break;
        }
        const ok = this._studio._bornNode?.(wsId, viewerShape, {
          durationMs: 400,
        });
        if (ok === true) {
          this._wsIdToSynthId.set(wsId, synthId);
        }
        break;
      }

      case "edge_added": {
        if (inBootstrap && m.edge && typeof m.edge === "object") {
          this._bootstrapBuffer.edges.push(m.edge as Record<string, unknown>);
          break;
        }
        if (!this._bootstrapBuffer.completed) {
          // eslint-disable-next-line no-console
          console.debug(
            "[t2-slice6a] edge_added pre-bootstrap-complete (live dropped)",
            m
          );
          break;
        }
        if (this._shouldDropLivePlanetDelta()) {
          // eslint-disable-next-line no-console
          console.debug(
            "[t2-slice6b] live delta dropped, viewContext=",
            this._viewContext,
            "verb=",
            t
          );
          return;
        }
        const edge = m.edge;
        if (!edge || typeof edge !== "object") {
          // eslint-disable-next-line no-console
          console.debug("[t2-slice6a] edge_added missing edge payload", m);
          break;
        }
        const eo = edge as Record<string, unknown>;
        // Workspace endpoint ids (not synth ids); resolve via _wsIdToSynthId.
        const fromWs = eo.from_id;
        const toWs = eo.to_id;
        if (typeof fromWs !== "string" || typeof toWs !== "string") {
          // eslint-disable-next-line no-console
          console.debug("[t2-slice6a] edge_added missing from_id/to_id", m);
          break;
        }
        const fromSynth = this._wsIdToSynthId.get(fromWs);
        const toSynth = this._wsIdToSynthId.get(toWs);
        if (!fromSynth || !toSynth) {
          // eslint-disable-next-line no-console
          console.debug("[t2-slice6a] edge_added unresolved endpoint", {
            fromWs,
            toWs,
          });
          break;
        }
        const ok = this._studio._bornEdge?.(fromSynth, toSynth);
        if (!ok) {
          // eslint-disable-next-line no-console
          console.debug("[t2-slice6a] edge_added unresolved or duplicate", {
            fromWs,
            toWs,
          });
        }
        break;
      }

      case "stats": {
        if (inBootstrap) {
          this._bootstrapBuffer.lastStats = {
            files: m.files,
            functions: m.functions,
            classes: m.classes,
            edges: m.edges,
            dark_matter: m.dark_matter,
            entangled: m.entangled,
          };
        } else {
          this._logDispatch(m, t);
        }
        break;
      }

      case "bootstrap_complete": {
        if (this._bootstrapBuffer.snapshotDone) break;
        this._bootstrapBuffer.completed = true;
        this._bootstrapBuffer.snapshotDone = true;
        // eslint-disable-next-line no-console
        console.debug(
          "[t2-slice2] bootstrap_complete — rebuilding",
          this._bootstrapBuffer.nodes.length,
          "nodes,",
          this._bootstrapBuffer.edges.length,
          "edges"
        );
        this._renderBufferedSnapshot();
        break;
      }

      case "node_modified": {
        if (this._shouldDropLivePlanetDelta()) {
          // eslint-disable-next-line no-console
          console.debug(
            "[t2-slice6b] live delta dropped, viewContext=",
            this._viewContext,
            "verb=",
            t
          );
          return;
        }
        const wsId =
          typeof m.node_id === "string" ? m.node_id : null;
        if (!wsId) {
          // eslint-disable-next-line no-console
          console.debug("[t2-slice3] node_modified missing node_id");
          break;
        }
        const synthId = this._wsIdToSynthId.get(wsId);
        if (synthId) {
          // eslint-disable-next-line no-console
          console.debug("[t2-slice3] node_modified", wsId, "->", synthId);
          this._studio._flashNodeRim?.(synthId, {
            color: 0xffffff,
            durationMs: 200,
          });
        } else {
          // eslint-disable-next-line no-console
          console.debug("[t2-slice3] node_modified for unknown id", wsId);
        }
        break;
      }

      case "node_removed": {
        if (this._shouldDropLivePlanetDelta()) {
          // eslint-disable-next-line no-console
          console.debug(
            "[t2-slice6b] live delta dropped, viewContext=",
            this._viewContext,
            "verb=",
            t
          );
          return;
        }
        const wsId =
          typeof m.node_id === "string" ? m.node_id : null;
        if (!wsId) {
          // eslint-disable-next-line no-console
          console.debug("[t2-slice4] node_removed missing node_id");
          break;
        }
        const synthId = this._wsIdToSynthId.get(wsId);
        if (synthId) {
          // eslint-disable-next-line no-console
          console.debug("[t2-slice4] node_removed", wsId, "->", synthId);
          this._studio._fadeAndRemoveNode?.(synthId, {
            durationMs: 400,
          });
          this._wsIdToSynthId.delete(wsId);
        } else {
          // eslint-disable-next-line no-console
          console.debug("[t2-slice4] node_removed for unknown id", wsId);
        }
        break;
      }

      case "edge_removed":
      case "error":
      case "pong":
        this._logDispatch(m, t);
        break;

      default:
        this._logDispatch(m, t);
    }
  }

  destroy() {
    this._studio._destroy?.();
  }
}
