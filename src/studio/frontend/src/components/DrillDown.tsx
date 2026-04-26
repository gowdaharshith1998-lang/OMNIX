import type { ReactNode } from "react";

type NodeSummary = {
  id: string;
  name: string;
  type: string;
  file_path?: string | null;
} | null;

type Props = { node: NodeSummary; extra?: ReactNode };

export function DrillDown({ node, extra }: Props) {
  return (
    <aside className="w-72 shrink-0 border-l border-studio-line bg-studio-panel/70 p-3 text-xs text-slate-300">
      <div className="mb-2 font-mono text-[10px] uppercase text-studio-muted">
        Inspector
      </div>
      {node ? (
        <div className="space-y-1">
          <div>
            <span className="text-studio-muted">name</span>{" "}
            <span className="text-white">{node.name}</span>
          </div>
          <div>
            <span className="text-studio-muted">type</span>{" "}
            <span className="text-sky-300">{node.type}</span>
          </div>
          {node.file_path && (
            <div className="break-all">
              <span className="text-studio-muted">file</span> {node.file_path}
            </div>
          )}
          <div className="break-all font-mono text-[10px] text-slate-500">
            {node.id}
          </div>
        </div>
      ) : (
        <p className="text-studio-muted">Select a node in the graph (coming soon).</p>
      )}
      {extra}
    </aside>
  );
}
