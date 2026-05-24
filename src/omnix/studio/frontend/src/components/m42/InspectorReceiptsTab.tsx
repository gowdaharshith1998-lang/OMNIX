import { useEffect, useRef, useState } from "react";

type ReceiptEntry = {
  id: string;
  label: string;
  ts: number;
  hashShort: string;
  verified: boolean | null;
};

type Props = {
  receipts: ReceiptEntry[];
  onRefresh: () => Promise<void> | void;
  onVerify: (id: string) => Promise<boolean | null> | boolean | null;
};

function ts(ms: number) {
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) return "--";
  return date.toLocaleString(undefined, {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

export function InspectorReceiptsTab({ receipts, onRefresh, onVerify }: Props) {
  const [refreshing, setRefreshing] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [state, setState] = useState<Record<string, boolean | null>>(() =>
    Object.fromEntries(receipts.map((r) => [r.id, r.verified]))
  );
  const mountedRef = useRef(true);
  useEffect(() => () => { mountedRef.current = false; }, []);

  useEffect(() => {
    setState((prev) => {
      const next: Record<string, boolean | null> = {};
      for (const r of receipts) {
        next[r.id] = r.id in prev ? prev[r.id] : r.verified;
      }
      return next;
    });
  }, [receipts]);

  const doRefresh = async () => {
    setRefreshing(true);
    try {
      await onRefresh();
    } finally {
      if (mountedRef.current) setRefreshing(false);
    }
  };

  const doVerify = async (id: string) => {
    setBusy(id);
    try {
      const result = await onVerify(id);
      if (mountedRef.current) {
        setState((prev) => ({ ...prev, [id]: result ?? null }));
      }
    } finally {
      if (mountedRef.current) setBusy(null);
    }
  };

  return (
    <div style={{ padding: 14, display: "flex", flexDirection: "column", gap: 12, height: "100%", overflowY: "auto" }}>
      <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
        <span className="m42-xray-eyebrow">Receipts</span>
        <button
          type="button"
          className="m42-btn is-ghost"
          onClick={doRefresh}
          disabled={refreshing}
        >
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </div>
      {receipts.length === 0 ? (
        <div className="m42-xray-card" style={{ color: "var(--m42-text-tertiary)" }}>
          No signed receipts yet for this workspace. They appear after the first
          gate-pass.
        </div>
      ) : (
        receipts.map((r) => {
          const status = state[r.id];
          let badge = "Verify";
          let className = "m42-btn";
          if (status === true) {
            badge = "Verified ✓";
            className += " is-primary";
          } else if (status === false) {
            badge = "Failed";
            className += " is-danger";
          }
          return (
            <div key={r.id} className="m42-xray-card">
              <div style={{ display: "flex", justifyContent: "space-between", gap: 8 }}>
                <div style={{ minWidth: 0 }}>
                  <div style={{ fontFamily: "var(--omnix-font-mono)", fontSize: 12 }}>
                    {r.label}
                  </div>
                  <div className="m42-card-hint">
                    {ts(r.ts)} · {r.hashShort}
                  </div>
                </div>
                <button
                  type="button"
                  className={className}
                  onClick={() => doVerify(r.id)}
                  disabled={busy === r.id}
                >
                  {busy === r.id ? "Verifying…" : badge}
                </button>
              </div>
            </div>
          );
        })
      )}
    </div>
  );
}

export type { ReceiptEntry };
