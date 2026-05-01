import { useEffect, useState } from "react";
import { getFile } from "@/lib/api";
import type { GraphNode } from "@/types/drilldown";
import type { XRayIssue } from "@/lib/xray_diagnostics";
import type { XRayInnerTab } from "./XRayItabs";

type Conn = {
  direction: "out" | "in";
  name: string;
  path: string;
  type: string;
};

type ScopeModel = {
  connections: Conn[];
  incoming: number;
  outgoing: number;
  dark: number;
};

type Props = {
  active: XRayInnerTab;
  workspaceId: string;
  scopeAtomId: string;
  selectedNode: GraphNode | null;
  scopeModel: ScopeModel;
  issues: XRayIssue[];
  filesystemHygieneCleanLine: string | null;
  onSuggestedAction: () => void;
};

function isSymbol(node: GraphNode | null) {
  return (
    node != null && ["function", "method", "class"].includes(node.type)
  );
}

function DiagnosticsBody({
  scopeAtomId,
  issues,
  onSuggestedAction,
  filesystemHygieneCleanLine,
}: {
  scopeAtomId: string;
  issues: XRayIssue[];
  onSuggestedAction: () => void;
  filesystemHygieneCleanLine: string | null;
}) {
  if (issues.length === 0) {
    return (
      <div className="space-y-2">
        {filesystemHygieneCleanLine ? (
          <div
            data-testid="xray-fs-hygiene-clean"
            className="rounded border border-emerald-500/25 bg-[rgba(16,185,129,0.06)] px-3 py-2 font-mono text-[11px] text-emerald-200/90"
          >
            {filesystemHygieneCleanLine}
          </div>
        ) : null}
        <div
          data-testid="xray-diagnostics-healthy"
          className="xray-ok rounded border border-omnix-accent-indigo/15 bg-[rgba(99,102,241,0.06)] px-3 py-2 font-mono text-[11px] text-omnix-text-muted"
        >
          No issues detected — this scope looks healthy.
          <span data-testid="xray-diagnostics-scope-key" className="hidden">
            {scopeAtomId}
          </span>
        </div>
      </div>
    );
  }
  return (
    <div className="xray-issues space-y-2">
      <span data-testid="xray-diagnostics-scope-key" className="hidden">
        {scopeAtomId}
      </span>
      {filesystemHygieneCleanLine ? (
        <div
          data-testid="xray-fs-hygiene-clean"
          className="rounded border border-emerald-500/25 bg-[rgba(16,185,129,0.06)] px-3 py-2 font-mono text-[11px] text-emerald-200/90"
        >
          {filesystemHygieneCleanLine}
        </div>
      ) : null}
      {issues.map((issue) => (
        <article
          key={`${issue.title}:${issue.action}`}
          className={`xray-issue rounded border px-3 py-2 ${issue.severity}`}
        >
          <strong className="font-mono text-xs text-omnix-text-primary">
            {issue.icon} {issue.title}
          </strong>
          <p className="mt-1 text-[11px] text-omnix-text-muted">{issue.detail}</p>
          <button
            type="button"
            className="mt-2 rounded border border-omnix-accent-indigo/30 px-2 py-1 font-mono text-[10px] uppercase text-omnix-accent-indigo transition hover:bg-[rgba(99,102,241,0.12)]"
            onClick={onSuggestedAction}
          >
            {issue.action}
          </button>
        </article>
      ))}
    </div>
  );
}

export function XRayContent({
  active,
  workspaceId,
  scopeAtomId,
  selectedNode,
  scopeModel,
  issues,
  filesystemHygieneCleanLine,
  onSuggestedAction,
}: Props) {
  const [codeBody, setCodeBody] = useState<string | null>(null);
  const [codeErr, setCodeErr] = useState<string | null>(null);

  useEffect(() => {
    if (active !== "code") return;
    const sym = isSymbol(selectedNode) ? selectedNode : null;
    const path = sym?.file_path;
    if (!path) {
      setCodeBody(null);
      setCodeErr(null);
      return;
    }
    let cancelled = false;
    setCodeErr(null);
    void getFile(workspaceId, path)
      .then((f) => {
        if (!cancelled) setCodeBody(f.content ?? "");
      })
      .catch(() => {
        if (!cancelled) {
          setCodeBody(null);
          setCodeErr("Could not load file");
        }
      });
    return () => {
      cancelled = true;
    };
  }, [active, workspaceId, selectedNode]);

  if (active === "agent") {
    return (
      <section className="xray-agent space-y-2 font-mono text-[11px] text-omnix-text-muted">
        <p>Quick actions</p>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            className="rounded-md border border-omnix-accent-indigo/35 px-2 py-1 text-[10px] uppercase text-omnix-text-primary transition hover:bg-[rgba(99,102,241,0.12)]"
            onClick={onSuggestedAction}
          >
            Explain selection
          </button>
          <button
            type="button"
            className="rounded-md border border-omnix-accent-indigo/35 px-2 py-1 text-[10px] uppercase text-omnix-text-primary transition hover:bg-[rgba(99,102,241,0.12)]"
            onClick={onSuggestedAction}
          >
            Find callers
          </button>
        </div>
      </section>
    );
  }

  if (active === "diagnostics") {
    return (
      <DiagnosticsBody
        scopeAtomId={scopeAtomId}
        issues={issues}
        onSuggestedAction={onSuggestedAction}
        filesystemHygieneCleanLine={filesystemHygieneCleanLine}
      />
    );
  }

  if (active === "history") {
    return (
      <p className="font-mono text-[11px] text-omnix-text-muted">
        Workspace revision history lives in the{" "}
        <span className="text-omnix-text-primary">History</span> panel tab in the
        right rail.
      </p>
    );
  }

  /* Code */
  if (selectedNode != null && isSymbol(selectedNode)) {
    const sym = selectedNode;
    return (
      <div data-testid="xray-code-body" className="space-y-3">
        <section>
          <h3 className="mb-1 font-mono text-[10px] uppercase tracking-[0.15em] text-omnix-text-dim">
            Signature
          </h3>
          <div className="xray-signature rounded border border-omnix-accent-indigo/20 bg-[rgba(2,6,21,0.4)] px-2 py-2 font-mono text-[11px] text-omnix-text-primary">
            {sym.name}
            <span className="mt-1 block text-omnix-text-muted">
              {sym.file_path}:{sym.line_start}
            </span>
          </div>
        </section>
        <Connections scopeModel={scopeModel} />
        {codeErr ? (
          <p className="text-[11px] text-omnix-text-muted">{codeErr}</p>
        ) : (
          <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded border border-omnix-accent-indigo/20 bg-[rgba(2,6,21,0.55)] p-2 font-mono text-[10px] leading-relaxed text-omnix-text-primary">
            {(codeBody ?? "").trim() ? codeBody : "Loading…"}
          </pre>
        )}
      </div>
    );
  }

  return (
    <div data-testid="xray-code-body" className="space-y-3">
      <Connections scopeModel={scopeModel} />
      <p className="font-mono text-[11px] text-omnix-text-muted">
        Select a function or class in the constellation to load source in this tab.
      </p>
    </div>
  );
}

function Connections({ scopeModel }: { scopeModel: ScopeModel }) {
  return (
    <section>
      <h3 className="mb-1 font-mono text-[10px] uppercase tracking-[0.15em] text-omnix-text-dim">
        Connections
      </h3>
      <div className="xray-connection-summary mb-2 font-mono text-[10px] text-omnix-text-muted">
        {scopeModel.outgoing} outgoing · {scopeModel.incoming} incoming ·{" "}
        {scopeModel.dark} dark
      </div>
      <div className="xray-list max-h-40 space-y-1 overflow-auto">
        {scopeModel.connections.map((conn, idx) => (
          <div
            key={`${conn.name}:${conn.type}:${idx}`}
            className="xray-connection-row flex justify-between gap-2 font-mono text-[10px] text-omnix-text-primary"
          >
            <span className="min-w-0 truncate">
              {conn.direction === "out" ? "→" : "←"} {conn.name}
            </span>
            <b className={`shrink-0 rel-${conn.type.toLowerCase()}`}>{conn.type}</b>
          </div>
        ))}
        {scopeModel.connections.length === 0 ? (
          <div className="xray-empty text-[10px] text-omnix-text-dim">
            No external connections.
          </div>
        ) : null}
      </div>
    </section>
  );
}
