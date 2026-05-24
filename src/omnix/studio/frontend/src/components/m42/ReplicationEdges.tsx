import { useMemo } from "react";

export type RepEdgePair = {
  id: string;
  sourceX: number;
  sourceY: number;
  targetX: number;
  targetY: number;
  inProgress?: boolean;
};

type Props = {
  pairs: RepEdgePair[];
  width: number;
  height: number;
};

export function ReplicationEdges({ pairs, width, height }: Props) {
  const paths = useMemo(() => {
    return pairs.map((pair) => {
      const dx = pair.targetX - pair.sourceX;
      const c1x = pair.sourceX + dx / 2;
      const c1y = pair.sourceY;
      const c2x = pair.sourceX + dx / 2;
      const c2y = pair.targetY;
      return {
        id: pair.id,
        d: `M${pair.sourceX},${pair.sourceY} C${c1x},${c1y} ${c2x},${c2y} ${pair.targetX},${pair.targetY}`,
        inProgress: !!pair.inProgress,
      };
    });
  }, [pairs]);

  return (
    <svg
      className="m42-rep-edges"
      width={width}
      height={height}
      viewBox={`0 0 ${Math.max(1, width)} ${Math.max(1, height)}`}
      aria-hidden
    >
      {paths.map((p) => (
        <path
          key={p.id}
          d={p.d}
          fill="none"
          stroke={p.inProgress ? "var(--m42-status-warning)" : "var(--m42-status-success)"}
          strokeWidth="1.2"
          strokeDasharray={p.inProgress ? "4 4" : "none"}
          opacity={p.inProgress ? 0.95 : 0.55}
        />
      ))}
    </svg>
  );
}
