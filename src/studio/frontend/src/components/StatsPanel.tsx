import type { ReactNode } from "react";
import { useScope } from "@/store/studioScopeStore";

type Stats = {
  files: number;
  functions: number;
  classes: number;
  edges: number;
  dark_matter?: number;
  entangled?: number;
};

type Props = {
  stats: Stats;
  /** Slice 15 — smaller blurred overlay inside the constellation canvas. */
  variant?: "default" | "constellation";
};

const row = "stat-row flex justify-between gap-4 font-mono text-xs leading-tight last:mb-0";

function Label({ children }: { children: ReactNode }) {
  return <span className="text-omnix-text-muted">{children}</span>;
}

export function StatsPanel({ stats, variant = "default" }: Props) {
  useScope();
  const shell =
    variant === "constellation"
      ? "omnix-glass pointer-events-auto min-w-[180px] rounded-lg px-3 py-2.5 backdrop-blur-md"
      : "omnix-glass pointer-events-auto min-w-[200px] rounded-xl px-4 py-3.5";
  return (
    <div className={shell}>
      <div className="mb-2 font-display text-[10px] font-bold uppercase tracking-[0.25em] text-[#a78bfa]">
        graph
      </div>
      <div className="space-y-1">
        <div className={row}>
          <Label>Files</Label>
          <span
            data-testid="stats-files"
            className="text-right"
            style={{ color: "var(--omnix-stat-mono)" }}
          >
            {stats.files}
          </span>
        </div>
        <div className={row}>
          <Label>Functions</Label>
          <span className="text-right" style={{ color: "var(--omnix-stat-mono)" }}>
            {stats.functions}
          </span>
        </div>
        <div className={row}>
          <Label>Classes</Label>
          <span className="text-right" style={{ color: "var(--omnix-stat-mono)" }}>
            {stats.classes}
          </span>
        </div>
        <div className={row}>
          <Label>Edges</Label>
          <span className="text-right" style={{ color: "var(--omnix-stat-mono)" }}>
            {stats.edges}
          </span>
        </div>
        {stats.dark_matter != null && (
          <div className={row}>
            <Label>Dark Matter</Label>
            <span
              className="text-right"
              style={{ color: "var(--omnix-stat-dark-matter)" }}
            >
              {stats.dark_matter}
            </span>
          </div>
        )}
        {stats.entangled != null && (
          <div className={row}>
            <Label>Entangled</Label>
            <span
              className="text-right"
              style={{ color: "var(--omnix-stat-entangled)" }}
            >
              {stats.entangled}
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
