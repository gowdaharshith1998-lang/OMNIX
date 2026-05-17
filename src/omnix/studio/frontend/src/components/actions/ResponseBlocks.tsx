import { useState } from "react";
import { splitCodeFences } from "@/lib/streamingChunker";
import type { ToolStep } from "@/lib/actions/types";

export function ResponseBlocks({ text }: { text: string }) {
  return (
    <div className="space-y-2">
      {splitCodeFences(text).map((part, index) =>
        part.kind === "code" ? (
          <pre
            key={index}
            className="overflow-auto whitespace-pre-wrap rounded border border-omnix-accent-indigo/20 bg-slate-950/70 p-2 font-mono text-[11px] text-omnix-text-primary"
          >
            {part.text}
          </pre>
        ) : (
          <p key={index} className="whitespace-pre-wrap text-sm leading-6 text-omnix-text-muted">
            {part.text}
          </p>
        )
      )}
    </div>
  );
}

function turnHeading(turn: number, phase?: string): string {
  if (turn === 0 || phase === "seed") return "Seed context";
  return `Turn ${turn}`;
}

function capReasonLabel(reason: string): string {
  const map: Record<string, string> = {
    max_iterations: "max iterations",
    token_limit: "token budget",
    wall_clock: "time limit",
    per_turn_timeout: "single-turn timeout",
    per_tool_timeout: "tool timeout",
  };
  return map[reason] ?? reason.replace(/_/g, " ");
}

export function ToolSteps({
  steps,
  capped,
  capReason,
}: {
  steps: ToolStep[];
  capped?: boolean;
  capReason?: string | null;
}) {
  const [open, setOpen] = useState<Record<string, boolean>>({});
  if (!steps.length && !capped) return null;

  const sorted = [...steps].sort(
    (a, b) => (a.turn_number ?? 0) - (b.turn_number ?? 0)
  );
  const byTurn = new Map<number, ToolStep[]>();
  for (const s of sorted) {
    const t = s.turn_number ?? 0;
    if (!byTurn.has(t)) byTurn.set(t, []);
    byTurn.get(t)!.push(s);
  }
  const turns = [...byTurn.keys()].sort((a, b) => a - b);

  function toggle(key: string) {
    setOpen((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  return (
    <div className="rounded border border-omnix-accent-indigo/20 bg-[rgba(99,102,241,0.06)] p-2">
      {capped && capReason ? (
        <div className="mb-2 rounded border border-amber-400/35 bg-amber-400/10 px-2 py-1.5 text-[11px] text-amber-100">
          Stopped early at {capReasonLabel(capReason)}. Result may be partial.
        </div>
      ) : null}
      <div className="mb-1 font-mono text-[10px] uppercase tracking-[0.14em] text-omnix-text-dim">
        tool timeline
      </div>
      <div className="space-y-3">
        {turns.map((turn) => (
          <div key={`turn-${turn}`}>
            <div className="mb-1 font-mono text-[9px] uppercase tracking-[0.12em] text-omnix-text-dim">
              {turnHeading(turn, byTurn.get(turn)?.[0]?.phase)}
            </div>
            <div className="space-y-1">
              {(byTurn.get(turn) ?? []).map((step, idx) => {
                const key = `${turn}:${step.tool}:${idx}`;
                const expanded = !!open[key];
                const ok = step.status === "ok";
                return (
                  <div
                    key={key}
                    className="rounded border border-omnix-accent-indigo/15 bg-[rgba(2,6,21,0.35)]"
                  >
                    <button
                      type="button"
                      className="flex w-full items-center justify-between gap-2 px-2 py-1 text-left font-mono text-[10px] text-omnix-text-muted hover:bg-[rgba(99,102,241,0.08)]"
                      onClick={() => toggle(key)}
                    >
                      <span className="truncate text-omnix-text-primary">
                        → {step.tool}
                        {step.args_summary ? `(${step.args_summary})` : ""}
                      </span>
                      <span
                        className={
                          ok ? "text-emerald-300" : step.status === "degraded" ? "text-amber-200" : "text-rose-300"
                        }
                      >
                        {ok ? "✓" : step.status === "degraded" ? "⊙" : "✗"} {step.status}
                        {step.truncated ? " · capped" : ""}
                      </span>
                    </button>
                    {expanded ? (
                      <div className="space-y-1 border-t border-omnix-accent-indigo/10 px-2 py-1.5 font-mono text-[10px] text-omnix-text-muted">
                        <div className="text-omnix-text-dim">args</div>
                        <pre className="max-h-32 overflow-auto whitespace-pre-wrap rounded bg-slate-950/60 p-1">
                          {step.args_summary || "—"}
                        </pre>
                        <div className="text-omnix-text-dim">result</div>
                        <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-slate-950/60 p-1 text-[10px]">
                          {step.result !== undefined
                            ? JSON.stringify(step.result, null, 2)
                            : "—"}
                        </pre>
                        {step.error ? (
                          <p className="text-rose-200">{step.error}</p>
                        ) : null}
                      </div>
                    ) : null}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
