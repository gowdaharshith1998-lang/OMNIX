import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchGrammarStatus,
  fetchLlmBudget,
  fetchMutations,
  fetchUnknownExtensions,
  verifyReceipt,
  type GrammarRow,
  type LlmBudget,
  type MutationRow,
  type UnknownExtensionRow,
} from "@/lib/grammarApi";

type FetchState<T> = {
  data: T | null;
  error: string | null;
};

const POLL_MS = 10_000;

function formatParseModes(modes: Record<string, unknown>): string {
  const keys = Object.keys(modes ?? {});
  if (keys.length === 0) return "—";
  return keys.slice(0, 3).join(", ") + (keys.length > 3 ? "…" : "");
}

function formatLlmBudgetLine(b: LlmBudget | null): string {
  if (!b) return "LLM budget: not configured";
  const t = b.budget_total;
  const r = b.budget_remaining;
  const c = b.calls_today;
  if (t == null && r == null && c == null) return "LLM budget: not configured";
  const parts: string[] = ["LLM budget:"];
  if (c != null) parts.push(`${c} calls today`);
  if (t != null && r != null) parts.push(`(${r} remaining / ${t} total)`);
  else if (r != null) parts.push(`${r} remaining`);
  else if (t != null) parts.push(`${t} total cap`);
  return parts.join(" ");
}

function relativeTime(iso: string): string {
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

function truncate(s: string, n: number): string {
  if (s.length <= n) return s;
  return s.slice(0, n - 1) + "…";
}

type VerifyPhase = "idle" | "pending" | "ok" | "fail";

function SectionSkeleton() {
  return (
    <div className="animate-pulse space-y-2 rounded-lg border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.35)] p-3">
      <div className="h-3 w-1/3 rounded bg-omnix-text-muted/20" />
      <div className="h-3 w-full rounded bg-omnix-text-muted/15" />
      <div className="h-3 w-5/6 rounded bg-omnix-text-muted/15" />
    </div>
  );
}

export function GrammarHealthDrawer() {
  const [budget, setBudget] = useState<FetchState<LlmBudget>>({ data: null, error: null });
  const [grammars, setGrammars] = useState<FetchState<GrammarRow[]>>({
    data: null,
    error: null,
  });
  const [mutations, setMutations] = useState<FetchState<MutationRow[]>>({
    data: null,
    error: null,
  });
  const [unknowns, setUnknowns] = useState<FetchState<UnknownExtensionRow[]>>({
    data: null,
    error: null,
  });
  const [initialTick, setInitialTick] = useState(true);
  const [verifyPhase, setVerifyPhase] = useState<Record<string, VerifyPhase>>({});
  const [verifyDetail, setVerifyDetail] = useState<Record<string, string>>({});
  const clearTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  const runTick = useCallback(async () => {
    const [s, m, u, b] = await Promise.allSettled([
      fetchGrammarStatus(),
      fetchMutations(20),
      fetchUnknownExtensions(),
      fetchLlmBudget(),
    ]);

    setGrammars((prev) => ({
      data: s.status === "fulfilled" ? s.value.grammars : prev.data,
      error: s.status === "rejected" ? String(s.reason) : null,
    }));
    setMutations((prev) => ({
      data: m.status === "fulfilled" ? m.value.mutations : prev.data,
      error: m.status === "rejected" ? String(m.reason) : null,
    }));
    setUnknowns((prev) => ({
      data: u.status === "fulfilled" ? u.value.extensions : prev.data,
      error: u.status === "rejected" ? String(u.reason) : null,
    }));
    setBudget((prev) => ({
      data: b.status === "fulfilled" ? b.value : prev.data,
      error: b.status === "rejected" ? String(b.reason) : null,
    }));
    setInitialTick(false);
  }, []);

  useEffect(() => {
    void runTick();
    const id = window.setInterval(() => void runTick(), POLL_MS);
    return () => {
      clearInterval(id);
      for (const t of clearTimersRef.current.values()) clearTimeout(t);
      clearTimersRef.current.clear();
    };
  }, [runTick]);

  const scheduleClearVerify = (path: string) => {
    const prev = clearTimersRef.current.get(path);
    if (prev) clearTimeout(prev);
    const t = window.setTimeout(() => {
      setVerifyPhase((p) => {
        const { [path]: _, ...rest } = p;
        return rest;
      });
      setVerifyDetail((d) => {
        const { [path]: __, ...rest } = d;
        return rest;
      });
      clearTimersRef.current.delete(path);
    }, 5000);
    clearTimersRef.current.set(path, t);
  };

  const handleVerify = (receiptPath: string) => {
    const p = receiptPath.trim();
    if (!p) return;
    setVerifyPhase((s) => ({ ...s, [p]: "pending" }));
    void verifyReceipt(p)
      .then((r) => {
        setVerifyPhase((s) => ({ ...s, [p]: r.verified ? "ok" : "fail" }));
        setVerifyDetail((d) => ({ ...d, [p]: r.verifier_output }));
        scheduleClearVerify(p);
      })
      .catch((e) => {
        const msg = e instanceof Error ? e.message : String(e);
        setVerifyPhase((s) => ({ ...s, [p]: "fail" }));
        setVerifyDetail((d) => ({ ...d, [p]: msg }));
        scheduleClearVerify(p);
      });
  };

  const VerifyCtl = ({ path }: { path: string }) => {
    const phase = verifyPhase[path] ?? "idle";
    const detail = verifyDetail[path] ?? "";
    const pending = phase === "pending";
    return (
      <span className="inline-flex items-center gap-1.5">
        <button
          type="button"
          disabled={pending}
          className="rounded border border-[var(--omnix-shell-border)] px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em] text-omnix-text-muted hover:text-omnix-text-primary disabled:cursor-wait disabled:opacity-60"
          title={detail || "Verify cryptographic receipt"}
          onClick={() => handleVerify(path)}
        >
          {pending ? "…" : "Verify"}
        </button>
        {phase === "ok" ? (
          <span
            className="font-mono text-[10px] text-emerald-400"
            title={detail}
          >
            ✓
          </span>
        ) : null}
        {phase === "fail" ? (
          <span className="font-mono text-[10px] text-rose-300" title={detail}>
            ✗
          </span>
        ) : null}
      </span>
    );
  };

  return (
    <div className="p-3" data-testid="grammar-health-drawer">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-omnix-text-dim">
          grammar health
        </div>
        <button
          type="button"
          className="rounded border border-[var(--omnix-shell-border)] px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-omnix-text-muted hover:text-omnix-text-primary"
          onClick={() => void runTick()}
        >
          Refresh
        </button>
      </div>

      {/* LLM budget */}
      <section className="mb-4" aria-label="LLM budget">
        {initialTick && budget.data === null && !budget.error ? (
          <SectionSkeleton />
        ) : budget.error ? (
          <div className="rounded-lg border border-rose-500/30 bg-rose-950/20 px-2 py-1.5 font-mono text-[10px] text-rose-200">
            Budget: {budget.error}
          </div>
        ) : (
          <div className="rounded-lg border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.5)] px-3 py-2 font-mono text-[11px] leading-relaxed text-omnix-text-muted">
            {formatLlmBudgetLine(budget.data)}
          </div>
        )}
      </section>

      {/* Grammars */}
      <section className="mb-4" aria-label="Grammars">
        <div className="mb-2 font-display text-xs font-bold uppercase tracking-[0.18em] text-omnix-text-primary">
          Grammars
        </div>
        {initialTick && grammars.data === null && !grammars.error ? (
          <SectionSkeleton />
        ) : grammars.error ? (
          <div className="text-sm text-rose-300/90">Failed to load grammars: {grammars.error}</div>
        ) : !grammars.data || grammars.data.length === 0 ? (
          <div className="text-sm text-omnix-text-dim">No grammar profiles yet.</div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] border-collapse text-left font-mono text-[10px]">
              <thead>
                <tr className="border-b border-[var(--omnix-shell-border)] text-omnix-text-dim">
                  <th className="py-1.5 pr-2 font-medium">Language</th>
                  <th className="py-1.5 pr-2 font-medium">Files</th>
                  <th className="py-1.5 pr-2 font-medium">Avg Q</th>
                  <th className="py-1.5 pr-2 font-medium">Modes</th>
                  <th className="py-1.5 pr-2 font-medium">Patterns</th>
                  <th className="py-1.5 pr-2 font-medium">Mut 30d</th>
                  <th className="py-1.5 font-medium">Receipt</th>
                </tr>
              </thead>
              <tbody className="text-omnix-text-muted">
                {grammars.data.map((g) => (
                  <tr
                    key={g.grammar_name}
                    className="border-b border-[var(--omnix-shell-border)]/60"
                  >
                    <td className="py-1.5 pr-2 text-omnix-text-primary">{g.grammar_name}</td>
                    <td className="py-1.5 pr-2">{g.files_parsed}</td>
                    <td className="py-1.5 pr-2">{g.avg_quality?.toFixed?.(3) ?? "—"}</td>
                    <td className="max-w-[6rem] truncate py-1.5 pr-2 text-[9px]" title={formatParseModes(g.parse_modes)}>
                      {formatParseModes(g.parse_modes)}
                    </td>
                    <td className="py-1.5 pr-2">{g.active_patterns}</td>
                    <td className="py-1.5 pr-2">{g.recent_mutations_30d}</td>
                    <td className="py-1.5">
                      <div className="flex max-w-[14rem] items-center gap-1 truncate">
                        <span className="truncate" title={g.last_evolution_receipt ?? ""}>
                          {g.last_evolution_receipt
                            ? g.last_evolution_receipt.split("/").pop()
                            : "—"}
                        </span>
                        {g.last_evolution_receipt ? (
                          <VerifyCtl path={g.last_evolution_receipt} />
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>

      {/* Mutations */}
      <section className="mb-4" aria-label="Recent mutations">
        <div className="mb-2 font-display text-xs font-bold uppercase tracking-[0.18em] text-omnix-text-primary">
          Recent mutations
        </div>
        {initialTick && mutations.data === null && !mutations.error ? (
          <SectionSkeleton />
        ) : mutations.error ? (
          <div className="text-sm text-rose-300/90">Failed to load mutations: {mutations.error}</div>
        ) : !mutations.data || mutations.data.length === 0 ? (
          <div className="text-sm text-omnix-text-dim">No mutations recorded.</div>
        ) : (
          <div className="space-y-2">
            {mutations.data.map((row, idx) => {
              const key = `${row.grammar_name}-${row.observed_at}-${idx}`;
              const reason = row.node_type || "";
              const receipt = row.receipt_path?.trim();
              return (
                <details
                  key={key}
                  className="rounded-lg border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.5)] p-2.5"
                >
                  <summary className="cursor-pointer list-none font-mono text-xs text-omnix-text-primary [&::-webkit-details-marker]:hidden">
                    <div className="flex flex-wrap items-center gap-2">
                      <span className="rounded-full border border-omnix-accent-indigo/35 px-2 py-0.5 text-[9px] uppercase tracking-[0.12em] text-omnix-cyan">
                        {row.grammar_name}
                      </span>
                      <span className="text-omnix-text-muted">{row.action}</span>
                      <span className="ml-auto text-[10px] text-omnix-text-dim">
                        {relativeTime(row.observed_at)}
                      </span>
                    </div>
                  </summary>
                  <p
                    className="mt-2 text-xs leading-5 text-omnix-text-muted"
                    title={reason.length > 80 ? reason : undefined}
                  >
                    {truncate(reason, 80)}
                  </p>
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
                    <span className="truncate font-mono text-[10px] text-omnix-text-dim">
                      {receipt || "—"}
                    </span>
                    {receipt ? <VerifyCtl path={receipt} /> : null}
                  </div>
                </details>
              );
            })}
          </div>
        )}
      </section>

      {/* Unknown extensions */}
      <section aria-label="Unknown extensions">
        <div className="mb-2 font-display text-xs font-bold uppercase tracking-[0.18em] text-omnix-text-primary">
          Unknown extensions
        </div>
        {initialTick && unknowns.data === null && !unknowns.error ? (
          <SectionSkeleton />
        ) : unknowns.error ? (
          <div className="text-sm text-rose-300/90">
            Failed to load unknown extensions: {unknowns.error}
          </div>
        ) : !unknowns.data || unknowns.data.length === 0 ? (
          <div className="text-sm text-omnix-text-dim">No unknown extensions.</div>
        ) : (
          <ul className="space-y-1.5">
            {unknowns.data.map((row) => (
              <li
                key={row.ext}
                className="flex items-start justify-between gap-2 rounded border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.35)] px-2 py-1.5 font-mono text-[10px]"
              >
                <span className="min-w-0 break-all text-omnix-text-primary">{row.ext}</span>
                <span className="shrink-0 text-omnix-text-dim">
                  {relativeTime(row.first_seen_at)}
                </span>
                {row.raw_bytes_hex ? (
                  <span
                    className="shrink-0 text-amber-300"
                    title={row.raw_bytes_hex}
                    aria-label="Corrupt extension bytes"
                  >
                    ⚠️
                  </span>
                ) : null}
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
