import { useEffect, useRef, useState, type ReactNode } from "react";
import { ReplicationEdges, type RepEdgePair } from "./ReplicationEdges";
import type { RunState } from "./types";

type Props = {
  runState: RunState;
  sourceLabel: string;
  targetLabel: string;
  sourceSymbolCount: number;
  targetSymbolCount: number;
  targetTotal: number;
  renderSource: () => ReactNode;
  renderTarget: () => ReactNode;
  replicationPairs: RepEdgePair[];
};

export function SplitGraphContainer({
  runState,
  sourceLabel,
  targetLabel,
  sourceSymbolCount,
  targetSymbolCount,
  targetTotal,
  renderSource,
  renderTarget,
  replicationPairs,
}: Props) {
  const ref = useRef<HTMLDivElement | null>(null);
  const [dims, setDims] = useState({ width: 0, height: 0 });

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      for (const entry of entries) {
        const { width, height } = entry.contentRect;
        setDims({ width, height });
      }
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  const split = runState !== "idle";

  return (
    <div
      ref={ref}
      className="m42-graph-area"
      data-testid="m42-graph-area"
      data-split={split ? "true" : "false"}
      data-run-state={runState}
      style={{
        position: "relative",
        height: "100%",
        width: "100%",
        overflow: "hidden",
      }}
    >
      {split ? (
        <>
          <span className="m42-split-header m42-left">
            SOURCE · {sourceLabel} · {sourceSymbolCount} symbols
          </span>
          <span className="m42-split-header m42-right">
            TARGET · {targetLabel} · {targetSymbolCount} / {targetTotal}
          </span>
          <div
            style={{
              position: "absolute",
              inset: 0,
              display: "grid",
              gridTemplateColumns: "1fr 1fr",
            }}
          >
            <div style={{ position: "relative", overflow: "hidden" }}>
              {renderSource()}
            </div>
            <div style={{ position: "relative", overflow: "hidden" }}>
              {renderTarget()}
            </div>
          </div>
          <span className="m42-split-midline" aria-hidden />
          <ReplicationEdges pairs={replicationPairs} width={dims.width} height={dims.height} />
        </>
      ) : (
        <div style={{ position: "absolute", inset: 0 }}>
          {renderSource()}
        </div>
      )}
    </div>
  );
}
