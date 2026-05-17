import { useEffect, useState } from "react";
import { getFile } from "@/lib/api";
import type { GraphNode } from "@/types/drilldown";

export type BrainTabScopeModel = {
  connections: { direction: "out" | "in"; name: string; path: string; type: string }[];
  incoming: number;
  outgoing: number;
  dark: number;
};

type Props = {
  workspaceId: string;
  selectedNode: GraphNode | null;
  scopeModel: BrainTabScopeModel;
};

function isSymbol(node: GraphNode | null) {
  return node != null && ["function", "method", "class"].includes(node.type);
}

export function BrainTabContent({ workspaceId, selectedNode, scopeModel }: Props) {
  const [codeBody, setCodeBody] = useState<string | null>(null);
  const [codeErr, setCodeErr] = useState<string | null>(null);

  useEffect(() => {
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
  }, [workspaceId, selectedNode]);

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

function Connections({ scopeModel }: { scopeModel: BrainTabScopeModel }) {
  return (
    <section>
      <h3 className="mb-1 font-mono text-[10px] uppercase tracking-[0.15em] text-omnix-text-dim">
        Connections
      </h3>
      <div className="xray-connection-summary mb-2 font-mono text-[10px] text-omnix-text-muted">
        {scopeModel.outgoing} outgoing · {scopeModel.incoming} incoming · {scopeModel.dark}{" "}
        dark
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

