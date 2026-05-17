import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { getReceiptById, listReceipts, type ReceiptEntry } from "@/lib/api";
import {
  fetchFindingScans,
  verifyScan,
  type ScanSummary,
  type VerifyScanResult,
} from "@/lib/findingsApi";

type Props = {
  workspaceId: string;
};

type ReceiptDetailState =
  | { status: "idle" }
  | { status: "loading" }
  | { status: "loaded"; payload: unknown }
  | { status: "error"; message: string };

type DrawerTab = "evolution" | "findings";

type VerifyPhase = "idle" | "pending" | "ok" | "fail";

function sourceLabel(receipt: ReceiptEntry) {
  return `${receipt.source} / ${receipt.sig_alg}`;
}

function receiptKey(receipt: ReceiptEntry) {
  return receipt.receipt_id || `${receipt.path}:${receipt.hash_prefix}`;
}

function hasSignature(receipt: ReceiptEntry) {
  return Boolean(receipt.has_signature) || receipt.sig_alg !== "unsigned";
}

function signatureLabel(receipt: ReceiptEntry) {
  if (!hasSignature(receipt)) return "unsigned";
  if (receipt.verified) return "verified";
  return "signature invalid";
}

function signatureClass(receipt: ReceiptEntry) {
  if (!hasSignature(receipt)) return "border-slate-500/30 text-omnix-text-dim";
  if (receipt.verified) return "border-emerald-400/35 text-emerald-300";
  return "border-amber-400/35 text-amber-300";
}

function detailText(state: ReceiptDetailState | undefined) {
  if (!state || state.status === "idle") return "";
  if (state.status === "loading") return "Loading receipt...";
  if (state.status === "error") return state.message;
  try {
    return JSON.stringify(state.payload, null, 2);
  } catch {
    return String(state.payload);
  }
}

function relativeTime(iso: string | null): string {
  if (!iso) return "—";
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return iso;
  const sec = Math.round((t - Date.now()) / 1000);
  const abs = Math.abs(sec);
  const rtf = new Intl.RelativeTimeFormat("en", { numeric: "auto" });
  if (abs < 60) return rtf.format(sec, "second");
  if (abs < 3600) return rtf.format(Math.round(sec / 60), "minute");
  if (abs < 86400) return rtf.format(Math.round(sec / 3600), "hour");
  if (abs < 86400 * 30) return rtf.format(Math.round(sec / 86400), "day");
  return rtf.format(Math.round(sec / (86400 * 30)), "month");
}

function truncateScanId(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "…";
}

function TabButton(props: {
  active: boolean;
  children: ReactNode;
  onClick: () => void;
  testId?: string;
}) {
  return (
    <button
      type="button"
      data-testid={props.testId}
      className={`border-b-2 px-2 py-1.5 font-mono text-[10px] uppercase tracking-[0.14em] transition-colors ${
        props.active
          ? "border-omnix-cyan text-omnix-text-primary"
          : "border-transparent text-omnix-text-dim hover:text-omnix-text-muted"
      }`}
      onClick={props.onClick}
    >
      {props.children}
    </button>
  );
}

function FindingScansSection() {
  const [rows, setRows] = useState<ScanSummary[] | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [verifyPhase, setVerifyPhase] = useState<Record<string, VerifyPhase>>({});
  const [verifyDetail, setVerifyDetail] = useState<Record<string, string>>({});
  const [verifyPayload, setVerifyPayload] = useState<Record<string, VerifyScanResult>>({});
  const clearTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const load = useCallback(async () => {
    setLoading(true);
    setErr(null);
    try {
      const data = await fetchFindingScans();
      setRows(data.scans);
    } catch (e) {
      setErr(e instanceof Error ? e.message : "load failed");
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
    return () => {
      for (const t of clearTimersRef.current.values()) clearTimeout(t);
      clearTimersRef.current.clear();
    };
  }, [load]);

  const scheduleClearVerify = (id: string) => {
    const prev = clearTimersRef.current.get(id);
    if (prev) clearTimeout(prev);
    const t = window.setTimeout(() => {
      setVerifyPhase((p) => {
        const { [id]: _, ...rest } = p;
        return rest;
      });
      setVerifyDetail((d) => {
        const { [id]: __, ...rest } = d;
        return rest;
      });
      setVerifyPayload((d) => {
        const { [id]: ___, ...rest } = d;
        return rest;
      });
      clearTimersRef.current.delete(id);
    }, 5000);
    clearTimersRef.current.set(id, t);
  };

  const handleVerify = (scanId: string) => {
    setVerifyPhase((s) => ({ ...s, [scanId]: "pending" }));
    void verifyScan(scanId)
      .then((r) => {
        setVerifyPhase((s) => ({ ...s, [scanId]: r.verified ? "ok" : "fail" }));
        const detail = r.verified
          ? JSON.stringify(r.manifest_summary ?? {})
          : r.reason || "verification failed";
        setVerifyDetail((d) => ({ ...d, [scanId]: detail }));
        setVerifyPayload((d) => ({ ...d, [scanId]: r }));
        scheduleClearVerify(scanId);
      })
      .catch((e) => {
        const msg = e instanceof Error ? e.message : String(e);
        setVerifyPhase((s) => ({ ...s, [scanId]: "fail" }));
        setVerifyDetail((d) => ({ ...d, [scanId]: msg }));
        scheduleClearVerify(scanId);
      });
  };

  if (loading && rows === null) {
    return (
      <div className="text-sm text-omnix-text-dim" data-testid="findings-scans-loading">
        Loading scans…
      </div>
    );
  }

  return (
    <div data-testid="findings-scans-section">
      <div className="mb-2 flex items-center justify-end gap-2">
        <button
          type="button"
          className="rounded border border-[var(--omnix-shell-border)] px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-omnix-text-muted hover:text-omnix-text-primary"
          onClick={() => void load()}
        >
          Refresh
        </button>
      </div>
      {err ? (
        <div className="text-sm text-rose-300/90">Failed to load scans: {err}</div>
      ) : !rows || rows.length === 0 ? (
        <div className="text-sm text-omnix-text-dim">No finding scans yet.</div>
      ) : (
        <ul className="space-y-2">
          {rows.map((row) => {
            const phase = verifyPhase[row.scan_id] ?? "idle";
            const pending = phase === "pending";
            const summaryTip =
              phase === "ok" && verifyPayload[row.scan_id]
                ? JSON.stringify(verifyPayload[row.scan_id]!.manifest_summary ?? {}, null, 2)
                : verifyDetail[row.scan_id] ?? "";
            return (
              <li
                key={row.scan_id}
                className="rounded-lg border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.5)] p-2.5"
              >
                <div className="flex items-start justify-between gap-2">
                  <div className="min-w-0 font-mono text-xs text-omnix-text-primary">
                    <div className="truncate" title={row.scan_id}>
                      {truncateScanId(row.scan_id, 44)}
                    </div>
                    <div className="mt-1 text-[10px] text-omnix-text-dim">
                      {row.finding_count} findings · {relativeTime(row.scan_started_at)}
                    </div>
                  </div>
                  <span className="inline-flex shrink-0 flex-col items-end gap-1">
                    <span className="inline-flex items-center gap-1.5">
                      <button
                        type="button"
                        data-testid={`verify-scan-${row.scan_id}`}
                        disabled={pending}
                        className="rounded border border-[var(--omnix-shell-border)] px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em] text-omnix-text-muted hover:text-omnix-text-primary disabled:cursor-wait disabled:opacity-60"
                        title={summaryTip || "Verify scan receipts"}
                        onClick={() => handleVerify(row.scan_id)}
                      >
                        {pending ? "…" : "Verify"}
                      </button>
                      {phase === "ok" ? (
                        <span
                          className="rounded-full border border-emerald-400/35 px-2 py-0.5 font-mono text-[10px] text-emerald-300"
                          title={summaryTip}
                        >
                          ✓ verified
                        </span>
                      ) : null}
                      {phase === "fail" ? (
                        <span
                          className="max-w-[140px] truncate rounded-full border border-rose-500/35 px-2 py-0.5 font-mono text-[10px] text-rose-300"
                          title={verifyDetail[row.scan_id] ?? ""}
                        >
                          ✗ {verifyDetail[row.scan_id] ?? ""}
                        </span>
                      ) : null}
                    </span>
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      )}
    </div>
  );
}

export function ReceiptsDrawer({ workspaceId }: Props) {
  const [activeTab, setActiveTab] = useState<DrawerTab>("evolution");
  const [receipts, setReceipts] = useState<ReceiptEntry[]>([]);
  const [loading, setLoading] = useState(true);
  const [err, setErr] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<string, ReceiptDetailState>>({});

  useEffect(() => {
    let cancelled = false;
    const timer = setTimeout(() => {
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
    }, 150);
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [workspaceId]);

  useEffect(() => {
    setDetails({});
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

  const loadDetail = (receipt: ReceiptEntry) => {
    const key = receiptKey(receipt);
    const receiptId = receipt.receipt_id;
    if (!receiptId) {
      setDetails((prev) => ({
        ...prev,
        [key]: { status: "error", message: "Receipt id unavailable." },
      }));
      return;
    }
    const existing = details[key];
    if (existing?.status === "loading" || existing?.status === "loaded") return;
    setDetails((prev) => ({ ...prev, [key]: { status: "loading" } }));
    void getReceiptById(workspaceId, receiptId)
      .then((payload) => {
        setDetails((prev) => ({
          ...prev,
          [key]: { status: "loaded", payload },
        }));
      })
      .catch((e) => {
        setDetails((prev) => ({
          ...prev,
          [key]: {
            status: "error",
            message: e instanceof Error ? e.message : "Failed to load receipt.",
          },
        }));
      });
  };

  return (
    <div className="p-3" data-testid="receipts-drawer">
      <div className="mb-3 flex border-b border-zinc-700/80">
        <TabButton
          active={activeTab === "evolution"}
          onClick={() => setActiveTab("evolution")}
          testId="tab-evolution-receipts"
        >
          Evolution Receipts
        </TabButton>
        <TabButton
          active={activeTab === "findings"}
          onClick={() => setActiveTab("findings")}
          testId="tab-finding-scans"
        >
          Finding Scans
        </TabButton>
      </div>

      {activeTab === "evolution" ? (
        <>
          <div className="mb-3 flex items-center justify-between gap-2">
            <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-omnix-text-dim">
              audit log
            </div>
            <button
              type="button"
              className="rounded border border-[var(--omnix-shell-border)] px-2 py-1 font-mono text-[10px] text-omnix-text-muted hover:text-omnix-text-primary"
              onClick={exportBundle}
              disabled={receipts.length === 0 || loading}
            >
              export bundle
            </button>
          </div>
          {loading ? (
            <div className="text-sm text-omnix-text-dim">Loading receipts...</div>
          ) : err ? (
            <div className="text-sm text-rose-300/90">Receipts load failed: {err}</div>
          ) : receipts.length === 0 ? (
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
                        key={receiptKey(receipt)}
                        className="rounded-lg border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.5)] p-2.5"
                      >
                        <div className="flex items-start justify-between gap-2">
                          <div className="min-w-0">
                            <div className="truncate font-mono text-xs text-omnix-text-primary">
                              {receipt.kind}
                            </div>
                            <div className="mt-1 truncate font-mono text-[10px] text-omnix-text-dim">
                              {receipt.target || sourceLabel(receipt)}
                            </div>
                          </div>
                          <span
                            className={`shrink-0 rounded-full border px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em] ${signatureClass(receipt)}`}
                          >
                            {signatureLabel(receipt)}
                          </span>
                        </div>
                        <div className="mt-2 flex items-center justify-between gap-2 font-mono text-[10px] text-omnix-text-muted">
                          <span>{receipt.hash_prefix}</span>
                          <span>{new Date(receipt.mtime_iso).toLocaleTimeString()}</span>
                        </div>
                        <details
                          className="mt-2"
                          onToggle={(event) => {
                            if (event.currentTarget.open) loadDetail(receipt);
                          }}
                        >
                          <summary className="cursor-pointer select-none font-mono text-[10px] uppercase tracking-[0.12em] text-omnix-cyan">
                            JSON
                          </summary>
                          <pre className="mt-2 max-h-72 overflow-auto whitespace-pre-wrap break-words rounded border border-slate-700/60 bg-slate-950/50 p-2 font-mono text-[10px] leading-relaxed text-omnix-text-muted">
                            {detailText(details[receiptKey(receipt)])}
                          </pre>
                        </details>
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </>
      ) : (
        <FindingScansSection />
      )}
    </div>
  );
}
