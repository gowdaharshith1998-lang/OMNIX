import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
} from "react";
import { OmnixDomStubs } from "./OmnixDomStubs";
import { recordFromGraphPayload } from "@/lib/graphNode";
import { isT1Mode } from "@/lib/t1Mode";
import type { GraphEdge, GraphNode } from "@/types/drilldown";
import { StudioGraph, type StudioGraphOptions } from "./StudioGraph";

export type GraphCanvasHandle = {
  ingestMessage: (msg: unknown) => void;
};

type Props = {
  drillDownNodeId: string | null;
  onFunctionNodeClick: (nodeId: string) => void;
  onFileOrDirClick: (filePath: string) => void;
  onDeselect: () => void;
  /** T1: merge static `graph_data*.json` nodes so DrillDown can resolve function/class id → file + lines. */
  onT1GraphNodes?: (nodes: GraphNode[]) => void;
  onT1GraphEdges?: (edges: GraphEdge[]) => void;
};

/**
 * React mount for the transplanted analyze viewer. Graphics are in StudioGraph / viewerEngine.
 * `?t1=1` (or VITE_OMNIX_T1): loads bundled `src/web/graph_data_axiom_v2.json` — full T1 drill.
 * Default URL: empty graph; Studio connects WebSocket elsewhere (Workspace) for live bootstrap.
 */
export const GraphCanvas = forwardRef<GraphCanvasHandle, Props>(
  function GraphCanvas(
    {
      drillDownNodeId: _drillDownNodeId,
      onFunctionNodeClick,
      onFileOrDirClick,
      onDeselect,
      onT1GraphNodes,
      onT1GraphEdges,
    }: Props,
    ref
  ) {
    void _drillDownNodeId; // T2+ highlight
    const mountRef = useRef<HTMLDivElement>(null);
    const graphRef = useRef<StudioGraph | null>(null);
    const optionsRef = useRef<StudioGraphOptions>({
      onFunctionNodeClick,
      onFileOrDirClick,
      onDeselect,
    });
    const t1OnNodesRef = useRef<Props["onT1GraphNodes"]>(onT1GraphNodes);
    const t1OnEdgesRef = useRef<Props["onT1GraphEdges"]>(onT1GraphEdges);

    useEffect(() => {
      optionsRef.current = {
        onFunctionNodeClick,
        onFileOrDirClick,
        onDeselect,
      };
    }, [onFunctionNodeClick, onFileOrDirClick, onDeselect]);

    useEffect(() => {
      t1OnNodesRef.current = onT1GraphNodes;
    }, [onT1GraphNodes]);

    useEffect(() => {
      t1OnEdgesRef.current = onT1GraphEdges;
    }, [onT1GraphEdges]);

    useImperativeHandle(ref, () => ({
      ingestMessage: (msg: unknown) => {
        graphRef.current?.ingestDelta(msg);
      },
    }));

    useEffect(() => {
      const el = mountRef.current;
      if (!el) return;

      const t1 = isT1Mode();
      const g = new StudioGraph(el, {
        get onFunctionNodeClick() {
          return optionsRef.current.onFunctionNodeClick;
        },
        get onFileOrDirClick() {
          return optionsRef.current.onFileOrDirClick;
        },
        get onDeselect() {
          return optionsRef.current.onDeselect;
        },
        get onDrilldownCatalog() {
          return t1OnNodesRef.current;
        },
        get onDrilldownEdges() {
          return t1OnEdgesRef.current;
        },
      } as StudioGraphOptions);
      graphRef.current = g;

      if (t1) {
        void import("../../../../../web/graph_data_axiom_v2.json")
          .then(
            (mod: {
              default: {
                nodes: unknown[];
                links: unknown[];
                stats?: Record<string, unknown>;
              };
            }) => {
              g.loadInitial(mod.default.nodes, mod.default.links, mod.default.stats);
              const cb = t1OnNodesRef.current;
              if (cb) {
                const raw = mod.default.nodes as Record<string, unknown>[];
                const list: GraphNode[] = [];
                for (let i = 0; i < raw.length; i++) {
                  const rec = recordFromGraphPayload(raw[i]!);
                  if (rec) list.push(rec);
                }
                cb(list);
              }
              const edgeCb = t1OnEdgesRef.current;
              if (edgeCb) {
                const links = mod.default.links as Record<string, unknown>[];
                const list: GraphEdge[] = [];
                for (let i = 0; i < links.length; i++) {
                  const link = links[i]!;
                  const source = typeof link.source === "string" ? link.source : null;
                  const target = typeof link.target === "string" ? link.target : null;
                  if (source && target) {
                    list.push({
                      id: typeof link.id === "string" || typeof link.id === "number" ? link.id : i,
                      source_id: source,
                      target_id: target,
                      relationship: typeof link.type === "string" ? link.type : "CALLS",
                    });
                  }
                }
                edgeCb(list);
              }
            }
          )
          .catch((e) => {
            // eslint-disable-next-line no-console
            console.error("T1: failed to load graph sample module", e);
          });
      }

      return () => {
        g.destroy();
        graphRef.current = null;
      };
    }, []);

    return (
      <>
        <OmnixDomStubs />
        <div
          ref={mountRef}
          className="absolute inset-0 h-full w-full"
          data-omnix-graph="1"
        />
      </>
    );
  }
);

GraphCanvas.displayName = "GraphCanvas";
