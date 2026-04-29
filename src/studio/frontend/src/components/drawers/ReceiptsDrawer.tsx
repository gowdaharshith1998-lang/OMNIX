import { useEffect, useMemo, useState } from "react";
import { listReceipts, type ReceiptEntry } from "@/lib/api";

type Props = {
  workspaceId: string;
};

function sourceLabel(receipt: ReceiptEntry) {
  return `${receipt.source} / ${receipt.sig_alg}`;
}

export function ReceiptsDrawer({ workspaceId }: Props) {
  const [receipts, setReceipts] = useState<ReceiptEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    void listReceipts(workspaceId, { limit: 200 })
      .then((rows) => {
        if (!cancelled) setReceipts(rows);
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : "load failed");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const bySource = useMemo(() => {
    const map = new Map<string, ReceiptEntry[]>();
    for (const receipt of receipts) {
      const list = map.get(receipt.source) ?? [];
      list.push(receipt);
      map.set(receipt.source, list);
    }
    return Array.from(map.entries());
  }, [receipts]);

  const exportBundle = () => {
    const blob = new Blob([JSON.stringify({ receipts }, null, 2)], {
      type: "application/json",
    });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "omnix-receipts.json";
    a.click();
    URL.revokeObjectURL(a.href);
  };

  if (loading) return <div className="p-4 text-sm text-omnix-text-dim">Loading receipts...</div>;
  if (err) return <div className="p-4 text-sm text-rose-300/90">Receipts load failed: {err}</div>;

  return (
    <div className="p-3">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-omnix-text-dim">
          audit log
        </div>
        <button
          type="button"
          className="rounded border border-[var(--omnix-shell-border)] px-2 py-1 font-mono text-[10px] text-omnix-text-muted hover:text-omnix-text-primary"
          onClick={exportBundle}
          disabled={receipts.length === 0}
        >
          export bundle
        </button>
      </div>
      {receipts.length === 0 ? (
        <div className="text-sm text-omnix-text-dim">No receipts found.</div>
      ) : (
        <div className="space-y-4">
          {bySource.map(([source, rows]) => (
            <section key={source}>
              <div className="mb-2 font-display text-xs font-bold uppercase tracking-[0.18em] text-omnix-text-primary">
                {source}
              </div>
              <div className="space-y-2">
                {rows.map((receipt) => (
                  <div
                    key={`${receipt.path}:${receipt.hash_prefix}`}
                    className="rounded-lg border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.5)] p-2.5"
                  >
                    <div className="truncate font-mono text-xs text-omnix-text-primary">
                      {receipt.kind}
                    </div>
                    <div className="mt-1 truncate font-mono text-[10px] text-omnix-text-dim">
                      {receipt.target || sourceLabel(receipt)}
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-2 font-mono text-[10px] text-omnix-text-muted">
                      <span>{receipt.hash_prefix}</span>
                      <span>{new Date(receipt.mtime_iso).toLocaleTimeString()}</span>
                    </div>
                  </div>
                ))}
              </div>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}
