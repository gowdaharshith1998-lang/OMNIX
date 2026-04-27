// @ts-nocheck
import { installOmnixViewerEngine } from "./viewerEngine";

export type StudioGraphOptions = {
  onFunctionNodeClick?: (nodeId: string) => void;
  onFileOrDirClick?: (filePath: string) => void;
  onDeselect?: () => void;
};

type StudioHandle = {
  _container: HTMLElement;
  _options: StudioGraphOptions;
  _loadGraphFromData?: (data: unknown) => void;
  _ingestDelta?: (message: unknown) => void;
  _destroy?: () => void;
};

/**
 * Class wrapper for the transplanted analyze viewer (see viewerEngine.ts).
 * Graphics code lives in viewerEngine; this only holds the host object for installOmnixViewerEngine.
 */
export class StudioGraph {
  private _studio: StudioHandle;

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

  /** Day 11a T2+ — live WebSocket deltas (slice 1: log-only, no renderer/state). */
  ingestDelta(message: unknown) {
    const m = message as Record<string, unknown>;
    const t = typeof m.type === "string" ? m.type : "";
    switch (t) {
      case "bootstrap_start":
      case "bootstrap_complete":
        // eslint-disable-next-line no-console
        console.debug("[t2-slice1]", t, "");
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
        console.debug("[t2-slice1]", t, id);
        break;
      }
      case "node_modified":
      case "node_removed": {
        const id = m.node_id != null ? String(m.node_id) : "";
        // eslint-disable-next-line no-console
        console.debug("[t2-slice1]", t, id);
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
        console.debug("[t2-slice1]", t, br);
        break;
      }
      case "edge_removed": {
        const id = m.edge_id != null ? String(m.edge_id) : "";
        // eslint-disable-next-line no-console
        console.debug("[t2-slice1]", t, id);
        break;
      }
      case "stats": {
        const br = `files=${m.files ?? "?"}`;
        // eslint-disable-next-line no-console
        console.debug("[t2-slice1]", t, br);
        break;
      }
      case "error": {
        // eslint-disable-next-line no-console
        console.debug("[t2-slice1]", t, String(m.message ?? ""));
        break;
      }
      case "pong": {
        // eslint-disable-next-line no-console
        console.debug("[t2-slice1]", t, String(m.ts ?? ""));
        break;
      }
      default:
        // eslint-disable-next-line no-console
        console.debug("[t2-slice1] unknown", t || "(no type)");
    }
  }

  destroy() {
    this._studio._destroy?.();
  }
}
