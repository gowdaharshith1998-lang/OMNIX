import { useEffect, useMemo, useState } from "react";
import { listReceipts, type ReceiptEntry } from "@/lib/api";

type Props = {
  workspaceId: string;
};

function dayKey(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "Unknown";
  return d.toLocaleDateString(undefined, {
    month: "short",
    day: "numeric",
    year: "numeric",
  });
}

function timeLabel(iso: string) {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "--:--";
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function HistoryTab({ workspaceId }: Props) {
  const [receipts, setReceipts] = useState<ReceiptEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setErr(null);
    void listReceipts(workspaceId, { limit: 100 })
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

  const grouped = useMemo(() => {
    const map = new Map<string, ReceiptEntry[]>();
    for (const receipt of receipts) {
      const key = dayKey(receipt.mtime_iso);
      const list = map.get(key) ?? [];
      list.push(receipt);
      map.set(key, list);
    }
    return Array.from(map.entries());
  }, [receipts]);

  if (loading) {
    return <div className="p-4 text-sm text-omnix-text-dim">Loading history...</div>;
  }

  if (err) {
    return <div className="p-4 text-sm text-rose-300/90">History load failed: {err}</div>;
  }

  if (receipts.length === 0) {
    return (
      <div className="p-4 text-sm text-omnix-text-dim">
        No receipts found in ~/.omnix/receipts yet.
      </div>
    );
  }

  return (
    <div className="h-full overflow-auto p-3">
      <div className="mb-3 font-display text-xs font-bold uppercase tracking-[0.22em] text-omnix-text-primary">
        Signed History
      </div>
      <div className="space-y-4">
        {grouped.map(([day, rows]) => (
          <section key={day}>
            <div className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-omnix-text-dim">
              {day}
            </div>
            <div className="space-y-2">
              {rows.map((receipt) => (
                <div
                  key={`${receipt.path}:${receipt.mtime_iso}`}
                  className="rounded-lg border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.5)] p-3"
                >
                  <div className="flex items-center justify-between gap-3">
                    <div className="min-w-0">
                      <div className="truncate font-mono text-xs text-omnix-text-primary">
                        {receipt.kind}
                      </div>
                      <div className="mt-1 truncate font-mono text-[10px] text-omnix-text-dim">
                        {receipt.target || receipt.source}
                      </div>
                    </div>
                    <div className="shrink-0 text-right font-mono text-[10px] text-omnix-text-muted">
                      <div>{timeLabel(receipt.mtime_iso)}</div>
                      <div>{receipt.source}</div>
                    </div>
                  </div>
                  <div className="mt-2 flex items-center justify-between gap-2 font-mono text-[10px] text-omnix-text-dim">
                    <span>{receipt.sig_alg}</span>
                    <span>{receipt.hash_prefix}</span>
                  </div>
                </div>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
