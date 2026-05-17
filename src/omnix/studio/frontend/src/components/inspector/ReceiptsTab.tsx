import { useEffect, useMemo, useState } from "react";
import { listReceipts, type ReceiptEntry } from "@/lib/api";

type Props = {
  workspaceId: string;
};

type ViewReceipt = {
  id: string;
  tsIso: string;
  scheme: string;
  verifyStatus: "verified" | "unverified" | "unknown";
};

function schemeLabel(sigAlg: string | null | undefined): string {
  const raw = String(sigAlg ?? "").trim();
  if (!raw) return "unknown";
  return raw.toLowerCase();
}

function verifyLabel(r: ReceiptEntry): "verified" | "unverified" | "unknown" {
  const hasSig = Boolean(r.has_signature) || r.sig_alg !== "unsigned";
  if (!hasSig) return "unknown";
  return r.verified ? "verified" : "unverified";
}

function tsLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso || "—";
  return d.toLocaleString(undefined, { month: "short", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export function ReceiptsTab({ workspaceId }: Props) {
  const [receipts, setReceipts] = useState<ReceiptEntry[] | null>(null);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    setErr(null);
    setReceipts(null);
    void listReceipts(workspaceId, { limit: 100 })
      .then((rows) => {
        if (!cancelled) setReceipts(rows);
      })
      .catch((e) => {
        if (!cancelled) setErr(e instanceof Error ? e.message : "load failed");
      });
    return () => {
      cancelled = true;
    };
  }, [workspaceId]);

  const view = useMemo((): ViewReceipt[] => {
    const rows = receipts ?? [];
    return rows.slice(0, 100).map((r) => ({
      id: r.receipt_id || r.hash_prefix || r.path,
      tsIso: r.mtime_iso,
      scheme: schemeLabel(r.sig_alg),
      verifyStatus: verifyLabel(r),
    }));
  }, [receipts]);

  if (err) {
    return (
      <div className="rounded border border-rose-500/20 bg-[rgba(244,63,94,0.06)] px-3 py-2 font-mono text-[11px] text-rose-200/90">
        Could not load receipts: {err}
      </div>
    );
  }

  if (receipts == null) {
    return (
      <div className="rounded border border-omnix-accent-indigo/15 bg-[rgba(99,102,241,0.05)] px-3 py-2 font-mono text-[11px] text-omnix-text-muted">
        Loading receipts…
      </div>
    );
  }

  if (view.length === 0) {
    return (
      <div className="rounded border border-omnix-accent-indigo/15 bg-[rgba(99,102,241,0.05)] px-3 py-2 font-mono text-[11px] text-omnix-text-muted">
        No receipts yet.
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {view.map((r) => (
        <div
          key={`${r.id}:${r.tsIso}`}
          data-receipt-row="1"
          className="rounded border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.5)] px-3 py-2"
        >
          <div className="flex items-center justify-between gap-2">
            <div className="min-w-0 truncate font-mono text-[11px] text-omnix-text-primary">
              {r.id}
            </div>
            <div className="shrink-0 font-mono text-[10px] uppercase tracking-[0.12em] text-omnix-text-dim">
              {r.scheme}
            </div>
          </div>
          <div className="mt-1 flex items-center justify-between gap-2 font-mono text-[10px] text-omnix-text-muted">
            <span data-receipt-ts="1">{tsLabel(r.tsIso)}</span>
            <span>{r.verifyStatus}</span>
          </div>
        </div>
      ))}
    </div>
  );
}

