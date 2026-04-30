import type { GraphEdge, GraphNode } from "@/types/drilldown";

type Props = {
  scopedNodes: GraphNode[];
  scopedEdges: GraphEdge[];
};

function packageBuckets(filePaths: Iterable<string | null | undefined>): number {
  const tops = new Set<string>();
  for (const raw of filePaths) {
    const fp = (raw ?? "").replace(/\\/g, "/").trim();
    if (!fp) continue;
    const seg = fp.split("/").filter(Boolean)[0];
    if (seg) tops.add(seg);
  }
  return tops.size;
}

export function XRayMetrics({ scopedNodes, scopedEdges }: Props) {
  let calls = 0;
  let imports = 0;
  for (const e of scopedEdges) {
    const r = e.relationship ?? "";
    if (r === "IMPORTS") imports += 1;
    else if (r === "CALLS") calls += 1;
  }
  const packages = packageBuckets(scopedNodes.map((n) => n.file_path));

  const rows: { k: string; v: number }[] = [
    { k: "Packages (tree)", v: packages },
    { k: "Call edges", v: calls },
    { k: "Import edges", v: imports },
  ];

  return (
    <section className="xray-metrics mt-4 border-t border-omnix-accent-indigo/15 pt-3">
      <h3 className="mb-2 font-mono text-[10px] uppercase tracking-[0.15em] text-omnix-text-dim">
        Scope metrics
      </h3>
      <dl className="space-y-1 font-mono text-[11px]">
        {rows.map((r) => (
          <div key={r.k} className="flex justify-between gap-3">
            <dt className="text-omnix-text-muted">{r.k}</dt>
            <dd className="text-omnix-text-primary">{r.v}</dd>
          </div>
        ))}
      </dl>
    </section>
  );
}
