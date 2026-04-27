import {
  forwardRef,
  useEffect,
  useImperativeHandle,
  useRef,
} from "react";
import { OmnixDomStubs } from "./OmnixDomStubs";
import { recordFromGraphPayload } from "@/lib/graphNode";
import type { GraphNode } from "@/types/drilldown";
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
};

function isT1Mode() {
  if (import.meta.env.VITE_OMNIX_T1 === "1") return true;
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get("t1") === "1";
}

/**
 * React mount for the transplanted analyze viewer. Graphics are in StudioGraph / viewerEngine.
 * HALT 11a-T1: open with ?t1=1 — loads bundled `src/web/graph_data_axiom_v2.json` (same shape as
 * analyze `graph_data.json`) so static rendering works without extra HTTP routes.
 */
export const GraphCanvas = forwardRef<GraphCanvasHandle, Props>(
  function GraphCanvas(
    {
      drillDownNodeId: _drillDownNodeId,
      onFunctionNodeClick,
      onFileOrDirClick,
      onDeselect,
      onT1GraphNodes,
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
