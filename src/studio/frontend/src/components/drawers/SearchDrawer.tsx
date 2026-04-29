import { useEffect, useState } from "react";
import {
  searchWorkspace,
  type SearchKind,
  type SearchResult,
} from "@/lib/api";
import type { GraphNode } from "@/types/drilldown";

type Props = {
  workspaceId?: string | null;
  query: string;
  fallbackNodes?: GraphNode[];
  onQueryChange: (query: string) => void;
  onOpenResult: (result: SearchResult) => void;
};

const EMPTY_GRAPH_NODES: GraphNode[] = [];

function nodeKind(node: GraphNode): SearchResult["kind"] | null {
  if (node.type === "file") return "file";
  if (node.type === "function" || node.type === "method" || node.type === "class") {
    return "symbol";
  }
  return null;
}

function searchFallbackNodes(
  nodes: GraphNode[],
  query: string,
  kind: SearchKind,
  limit: number
) {
  const q = query.toLowerCase();
  const rows: SearchResult[] = [];
  for (const node of nodes) {
    const mappedKind = nodeKind(node);
    if (!mappedKind) continue;
    if (kind !== "all" && kind !== mappedKind) continue;
    const path = node.file_path ?? "";
    const haystack = `${node.name} ${node.id} ${path}`.toLowerCase();
    if (!haystack.includes(q)) continue;
    rows.push({
      kind: mappedKind,
      name: node.name,
      path,
      line: node.line_start || 0,
      snippet: "",
    });
    if (rows.length >= limit) break;
  }
  return rows;
}

export function SearchDrawer({
  workspaceId,
  query,
  fallbackNodes = EMPTY_GRAPH_NODES,
  onQueryChange,
  onOpenResult,
}: Props) {
  const [kind, setKind] = useState<SearchKind>("all");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    const q = query.trim();
    if (!q) {
      setResults([]);
      setLoading(false);
      setErr(null);
      return;
    }
    let cancelled = false;
    const timer = setTimeout(() => {
      setLoading(true);
      setErr(null);
      if (!workspaceId) {
        setResults(searchFallbackNodes(fallbackNodes, q, kind, 50));
        setLoading(false);
        return;
      }
      void searchWorkspace(workspaceId, q, kind, 50)
        .then((rows) => {
          if (!cancelled) setResults(rows);
        })
        .catch((e) => {
          if (!cancelled) setErr(e instanceof Error ? e.message : "search failed");
        })
        .finally(() => {
          if (!cancelled) setLoading(false);
        });
    }, 150);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [fallbackNodes, kind, query, workspaceId]);

  return (
    <div className="p-3">
      <div className="mb-3 font-mono text-[10px] uppercase tracking-[0.18em] text-omnix-text-dim">
        graph search
      </div>
      <input
        className="mb-2 w-full rounded border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.7)] px-2 py-1.5 font-mono text-sm text-omnix-text-primary outline-none focus:border-omnix-accent-indigo/60"
        value={query}
        onChange={(e) => onQueryChange(e.target.value)}
        placeholder="symbol, file, path..."
        type="search"
      />
      <div className="mb-3 flex gap-2">
        {(["all", "symbol", "file"] as SearchKind[]).map((item) => (
          <button
            key={item}
            type="button"
            className={
              "rounded border px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] " +
              (kind === item
                ? "border-omnix-accent-indigo/50 text-omnix-text-primary"
                : "border-[var(--omnix-shell-border)] text-omnix-text-dim")
            }
            onClick={() => setKind(item)}
          >
            {item}
          </button>
        ))}
      </div>
      {loading && <div className="text-sm text-omnix-text-dim">Searching...</div>}
      {err && <div className="text-sm text-rose-300/90">Search failed: {err}</div>}
      {!loading && !err && query.trim() && results.length === 0 && (
        <div className="text-sm text-omnix-text-dim">No graph matches.</div>
      )}
      <div className="space-y-2">
        {results.map((result) => (
          <button
            key={`${result.kind}:${result.path}:${result.line}:${result.name}`}
            type="button"
            className="block w-full rounded-lg border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.5)] p-2.5 text-left hover:border-omnix-accent-indigo/35"
            onClick={() => onOpenResult(result)}
          >
            <div className="flex items-center justify-between gap-2">
              <span className="truncate font-mono text-xs text-omnix-text-primary">
                {result.name || result.path}
              </span>
              <span className="shrink-0 font-mono text-[10px] uppercase text-omnix-text-dim">
                {result.kind}
              </span>
            </div>
            <div className="mt-1 truncate font-mono text-[10px] text-omnix-text-muted">
              {result.path}
              {result.line ? `:${result.line}` : ""}
            </div>
          </button>
        ))}
      </div>
    </div>
  );
}
