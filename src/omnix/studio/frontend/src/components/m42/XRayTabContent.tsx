import type { ReactNode } from "react";
import type { GraphSide } from "./types";

type Stats = {
  files: number;
  functions: number;
  classes: number;
  edges: number;
};

type Diagnostic = {
  id: string;
  title: string;
  hint?: string;
};

type Props = {
  side: GraphSide;
  scopeKind: "Repository" | "Module" | "File" | "Symbol";
  scopeLabel: string;
  scopePath?: string;
  stats: Stats;
  diagnostics?: Diagnostic[];
  onTargetAction?: (action: "source" | "receipt" | "diff") => void;
  emptyMessage?: ReactNode;
};

export function XRayTabContent({
  side,
  scopeKind,
  scopeLabel,
  scopePath,
  stats,
  diagnostics,
  onTargetAction,
  emptyMessage,
}: Props) {
  if (side === "target") {
    return (
      <div className="m42-target-menu" data-testid="m42-target-menu">
        <span className="m42-target-menu-eyebrow">target · {scopeKind}</span>
        <h3 className="m42-target-menu-title">{scopeLabel}</h3>
        {scopePath ? (
          <span className="m42-xray-subtitle">{scopePath}</span>
        ) : null}
        <button
          type="button"
          className="m42-target-menu-item"
          onClick={() => onTargetAction?.("source")}
        >
          <span>View generated source</span>
          <span className="m42-arrow">›</span>
        </button>
        <button
          type="button"
          className="m42-target-menu-item"
          onClick={() => onTargetAction?.("receipt")}
        >
          <span>View signed receipt</span>
          <span className="m42-arrow">›</span>
        </button>
        <button
          type="button"
          className="m42-target-menu-item"
          onClick={() => onTargetAction?.("diff")}
        >
          <span>Side-by-side diff (source ↔ target)</span>
          <span className="m42-arrow">›</span>
        </button>
      </div>
    );
  }

  return (
    <div className="m42-xray" data-testid="m42-xray-source">
      <div>
        <div className="m42-xray-eyebrow">{scopeKind}</div>
        <div className="m42-xray-title">{scopeLabel}</div>
        {scopePath ? <div className="m42-xray-subtitle">{scopePath}</div> : null}
      </div>
      <div className="m42-xray-metrics">
        <div className="m42-xray-metric">
          <div className="m42-xray-metric-value">{stats.files.toLocaleString()}</div>
          <div className="m42-xray-metric-label">Files</div>
        </div>
        <div className="m42-xray-metric">
          <div className="m42-xray-metric-value">{stats.functions.toLocaleString()}</div>
          <div className="m42-xray-metric-label">Call edges</div>
        </div>
        <div className="m42-xray-metric">
          <div className="m42-xray-metric-value">{stats.edges.toLocaleString()}</div>
          <div className="m42-xray-metric-label">Import edges</div>
        </div>
      </div>
      <div className="m42-xray-section">
        <h4>Diagnostics</h4>
        {diagnostics && diagnostics.length > 0 ? (
          diagnostics.map((diagnostic) => (
            <div key={diagnostic.id} className="m42-xray-card">
              <div>{diagnostic.title}</div>
              {diagnostic.hint ? (
                <div className="m42-card-hint">{diagnostic.hint}</div>
              ) : null}
            </div>
          ))
        ) : (
          <div className="m42-xray-card" style={{ color: "var(--m42-text-tertiary)" }}>
            {emptyMessage ?? "No smart-card diagnostics for this scope."}
          </div>
        )}
      </div>
    </div>
  );
}
