// @ts-nocheck
import type { GraphNode } from "@/types/drilldown";
import { isT1Mode } from "@/lib/t1Mode";
import {
  recordFromGraphPayload,
  wsEdgeToLinkShape,
  wsNodeToViewerShape,
} from "@/lib/graphNode";
import { installOmnixViewerEngine } from "./viewerEngine";

export type StudioGraphOptions = {
  onFunctionNodeClick?: (nodeId: string) => void;
  onFileOrDirClick?: (filePath: string) => void;
  onDeselect?: () => void;
  /** Same role as T1 `onT1GraphNodes`: DrillDown catalog after full graph snapshot. */
  onDrilldownCatalog?: (nodes: GraphNode[]) => void;
};

type StudioHandle = {
  _container: HTMLElement;
  _options: StudioGraphOptions;
  _loadGraphFromData?: (data: unknown) => void;
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
        } else if (!inBootstrap) {
          this._logDispatch(m, t);
        }
        break;
      }

      case "edge_added": {
        if (inBootstrap && m.edge && typeof m.edge === "object") {
          this._bootstrapBuffer.edges.push(m.edge as Record<string, unknown>);
        } else if (!inBootstrap) {
          this._logDispatch(m, t);
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
