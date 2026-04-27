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

  /** Day 11a T2+ — live WebSocket deltas (stub until wired). */
  ingestDelta(message: unknown) {
    this._studio._ingestDelta?.(message);
  }

  destroy() {
    this._studio._destroy?.();
  }
}
