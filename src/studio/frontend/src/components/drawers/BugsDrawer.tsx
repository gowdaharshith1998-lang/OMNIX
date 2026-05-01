import { useEffect, useMemo, useRef, useState } from "react";
import {
  BugsScanConflictError,
  startBugsScan,
  type BugFinding,
  type BugScanSummary,
  type BugsScanEvent,
} from "@/lib/api";

type Props = {
  workspaceId: string;
  scanEvent?: BugsScanEvent | null;
  onToast?: (message: string, durationMs?: number) => void;
};

type ScanStatus = "idle" | "starting" | "running" | "complete" | "error";
type SortMode = "rank" | "severity" | "file";
type SeverityTier = "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";

function severityTier(score: number, kind?: string): SeverityTier {
  if (score >= 20 || kind === "memory_pathology") return "CRITICAL";
  if (score >= 10) return "HIGH";
  if (score >= 4) return "MEDIUM";
  return "LOW";
}

function severityClass(tier: SeverityTier) {
  if (tier === "CRITICAL") return "border-rose-400/35 text-rose-300/90";
  if (tier === "HIGH") return "border-amber-400/35 text-amber-300";
  if (tier === "MEDIUM") return "border-yellow-400/35 text-yellow-300";
  return "border-sky-400/35 text-sky-300";
}

function scoreOf(finding: BugFinding) {
  return Number(finding.severity_score ?? 0);
}

function findingKey(finding: BugFinding, index: number) {
  return `${finding.file}:${finding.function}:${finding.lineno ?? 0}:${index}`;
}

function firstFailureText(finding: BugFinding) {
  const failure = finding.failures?.[0];
  if (!failure) return finding.reason || "Property-based verification found a failing input.";
  const kind = failure.exception_type || "Failure";
  const message = failure.message || failure.exception_message || finding.reason || "";
  return message ? `${kind}: ${message}` : kind;
}

function inputText(finding: BugFinding) {
  const failure = finding.failures?.[0];
  return failure?.shrunk_input || failure?.input || finding.input || "";
}

function formatElapsed(seconds: number) {
  if (!Number.isFinite(seconds) || seconds < 0) return "0s";
  if (seconds < 60) return `${Math.floor(seconds)}s`;
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60);
  return `${minutes}m ${rest}s`;
}

function summaryText(summary: BugScanSummary | null, findings: BugFinding[]) {
  if (!summary) return `${findings.length} finding${findings.length === 1 ? "" : "s"}`;
  const files = summary.files_scanned ?? 0;
  const examples = summary.total_examples_run ?? 0;
  const bud =
    summary.budget_used != null && summary.budget_total != null
      ? ` · budget ${summary.budget_used}/${summary.budget_total}`
      : "";
  return `${findings.length} finding${findings.length === 1 ? "" : "s"} / ${files} files / ${examples} examples${bud}`;
}

export function BugsDrawer({ workspaceId, scanEvent, onToast }: Props) {
  const [status, setStatus] = useState<ScanStatus>("idle");
  const [scanId, setScanId] = useState<string | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [scanPhase, setScanPhase] = useState<string | null>(null);
  const [budgetUsedLive, setBudgetUsedLive] = useState<number | null>(null);
  const [findings, setFindings] = useState<BugFinding[]>([]);
  const [summary, setSummary] = useState<BugScanSummary | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [sortMode, setSortMode] = useState<SortMode>("rank");
  const wallClockStartRef = useRef<number | null>(null);

  const scanning = status === "starting" || status === "running";

  useEffect(() => {
    if (!scanning) return;
    const start =
      wallClockStartRef.current !== null ? wallClockStartRef.current : Date.now();
    if (wallClockStartRef.current === null) {
      wallClockStartRef.current = start;
    }
    const id = window.setInterval(() => {
      setElapsed((Date.now() - start) / 1000);
    }, 250);
    return () => clearInterval(id);
  }, [scanning, scanId]);

  useEffect(() => {
    if (!scanEvent) return;
    if (scanEvent.type === "bugs_scan_started") {
      setScanId(scanEvent.scan_id);
      setStatus("running");
      if (wallClockStartRef.current === null) {
        wallClockStartRef.current = Date.now();
      }
      setElapsed(0);
      setScanPhase("dispatching");
      setBudgetUsedLive(null);
      setError(null);
      return;
    }
    if (scanEvent.type === "bugs_scan_heartbeat") {
      if (scanId != null && scanEvent.scan_id !== scanId) return;
      setScanId(scanEvent.scan_id);
      setStatus((current) => (current === "complete" ? current : "running"));
      setElapsed(scanEvent.elapsed_seconds);
      if (scanEvent.scan_phase) setScanPhase(scanEvent.scan_phase);
      if (scanEvent.budget_used != null) setBudgetUsedLive(scanEvent.budget_used);
      return;
    }
    if (scanEvent.type === "bugs_scan_complete") {
      setScanId(scanEvent.scan_id);
      setStatus("complete");
      setFindings(scanEvent.findings);
      setSummary(scanEvent.summary);
      setElapsed(scanEvent.wall_time_seconds);
      wallClockStartRef.current = null;
      setScanPhase(scanEvent.summary?.scan_phase ?? null);
      setBudgetUsedLive(scanEvent.summary?.budget_used ?? null);
      setError(null);
      return;
    }
    if (scanEvent.type === "bugs_scan_error") {
      setScanId(scanEvent.scan_id);
      setStatus("error");
      setError(scanEvent.error_message);
      wallClockStartRef.current = null;
      onToast?.(scanEvent.error_message, 3500);
    }
  }, [onToast, scanEvent, scanId]);

  const sortedFindings = useMemo(() => {
    const rows = findings.map((finding, index) => ({ finding, index }));
    if (sortMode === "severity") {
      rows.sort(
        (a, b) =>
          scoreOf(b.finding) - scoreOf(a.finding) ||
          a.finding.file.localeCompare(b.finding.file) ||
          a.finding.function.localeCompare(b.finding.function)
      );
    } else if (sortMode === "file") {
      rows.sort(
        (a, b) =>
          a.finding.file.localeCompare(b.finding.file) ||
          a.finding.function.localeCompare(b.finding.function) ||
          scoreOf(b.finding) - scoreOf(a.finding)
      );
    }
    return rows;
  }, [findings, sortMode]);

  const buttonLabel = scanning ? "Scanning..." : status === "complete" ? "RESCAN" : "SCAN";

  const beginScan = () => {
    setStatus("starting");
    setError(null);
    wallClockStartRef.current = null;
    void startBugsScan(workspaceId)
      .then(({ scan_id }) => {
        setScanId(scan_id);
        setStatus("running");
        wallClockStartRef.current = Date.now();
        setElapsed(0);
      })
      .catch((e) => {
        const message =
          e instanceof BugsScanConflictError
            ? "Scan already running, wait for current to complete."
            : e instanceof Error
              ? e.message
              : "Scan failed";
        setStatus(findings.length ? "complete" : "idle");
        setError(message);
        onToast?.(message, 3500);
      });
  };

  return (
    <div className="p-3">
      <div className="mb-3 flex items-center justify-between gap-2">
        <div className="font-mono text-[10px] uppercase tracking-[0.18em] text-omnix-text-dim">
          bugs
        </div>
        <button
          type="button"
          className="rounded border border-[var(--omnix-shell-border)] px-2 py-1 font-mono text-[10px] uppercase tracking-[0.12em] text-omnix-text-muted hover:text-omnix-text-primary disabled:cursor-wait disabled:opacity-60"
          onClick={beginScan}
          disabled={scanning}
        >
          {buttonLabel}
        </button>
      </div>

      <div className="mb-3 rounded-lg border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.5)] p-3">
        <div className="flex items-start justify-between gap-2">
          <div>
            <div className="font-display text-sm font-bold text-omnix-text-primary">
              PBT bug scan
            </div>
            <p className="mt-1 text-xs leading-5 text-omnix-text-dim">
              Runs the existing find_bugs property-based scanner against this workspace.
            </p>
          </div>
          {scanning && (
            <span className="shrink-0 rounded-full border border-omnix-accent-indigo/35 px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em] text-omnix-cyan">
              {formatElapsed(elapsed)}
            </span>
          )}
        </div>
        {scanId && (
          <div className="mt-2 truncate font-mono text-[10px] text-omnix-text-muted">
            scan {scanId}
          </div>
        )}
      </div>

      {scanning && (
        <div className="mb-3 text-sm text-omnix-text-dim">
          Scanning… {scanPhase ? `${scanPhase} · ` : ""}
          elapsed {formatElapsed(elapsed)}
          {budgetUsedLive != null ? ` · examples ${budgetUsedLive}` : ""}
        </div>
      )}
      {error && <div className="mb-3 text-sm text-rose-300/90">Scan failed: {error}</div>}
      {!scanning && !error && findings.length === 0 && (
        <div className="text-sm text-omnix-text-dim">
          No findings yet. Run SCAN to analyze this workspace.
        </div>
      )}

      {findings.length > 0 && (
        <>
          <div className="mb-3 flex items-center justify-between gap-2">
            <div className="font-mono text-[10px] uppercase tracking-[0.12em] text-omnix-text-muted">
              {summaryText(summary, findings)}
            </div>
            <div className="flex gap-1">
              {(["rank", "severity", "file"] as SortMode[]).map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className={
                    "rounded border px-2 py-1 font-mono text-[9px] uppercase tracking-[0.12em] " +
                    (sortMode === mode
                      ? "border-omnix-accent-indigo/50 text-omnix-text-primary"
                      : "border-[var(--omnix-shell-border)] text-omnix-text-dim")
                  }
                  onClick={() => setSortMode(mode)}
                >
                  {mode}
                </button>
              ))}
            </div>
          </div>
          <div className="space-y-2">
            {sortedFindings.map(({ finding, index }) => {
              const score = scoreOf(finding);
              const tier = severityTier(score, finding.kind);
              const location = `${finding.file}${finding.lineno ? `:${finding.lineno}` : ""}`;
              return (
                <article
                  key={findingKey(finding, index)}
                  className="rounded-lg border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.5)] p-2.5"
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="truncate font-mono text-xs text-omnix-text-primary">
                        {finding.function}
                      </div>
                      <div className="mt-1 truncate font-mono text-[10px] text-omnix-text-dim">
                        {location}
                      </div>
                    </div>
                    <div className="flex shrink-0 flex-col items-end gap-1">
                      {finding.dimension === "filesystem_hygiene" ? (
                        <span
                          className="rounded-full border border-cyan-400/40 px-2 py-0.5 font-mono text-[8px] uppercase tracking-[0.14em] text-cyan-200"
                          title="Filesystem hygiene dimension"
                        >
                          FS-HYGIENE
                        </span>
                      ) : null}
                      <span
                        className={`rounded-full border px-2 py-0.5 font-mono text-[9px] uppercase tracking-[0.12em] ${severityClass(tier)}`}
                        title={`severity score: ${score}`}
                      >
                        {tier}
                      </span>
                    </div>
                  </div>
                  <p className="mt-2 text-xs leading-5 text-omnix-text-muted">
                    {firstFailureText(finding)}
                  </p>
                  {finding.dimension === "filesystem_hygiene" &&
                  finding.offending_paths &&
                  finding.offending_paths.length > 0 ? (
                    <ul className="mt-2 max-h-24 list-inside list-disc overflow-y-auto rounded border border-slate-700/60 bg-slate-950/50 px-2 py-1 font-mono text-[10px] text-omnix-text-muted">
                      {finding.offending_paths.slice(0, 12).map((o) => (
                        <li key={o.path} className="truncate">
                          {o.path}
                          {typeof o.size === "number" ? ` (${o.size}b)` : ""}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {inputText(finding) && (
                    <div className="mt-2 truncate rounded border border-slate-700/60 bg-slate-950/50 px-2 py-1 font-mono text-[10px] text-omnix-text-muted">
                      input {inputText(finding)}
                    </div>
                  )}
                  <div className="mt-2 flex justify-end">
                    <button
                      type="button"
                      className="rounded border border-[var(--omnix-shell-border)] px-2 py-1 font-mono text-[9px] uppercase tracking-[0.12em] text-omnix-text-muted hover:text-omnix-text-primary"
                      onClick={() => {
                        if (finding.dimension === "filesystem_hygiene") {
                          const parts = [
                            finding.reproduction,
                            finding.fuzz_inputs,
                            finding.offending_paths
                              ?.map((o) => o.path)
                              .join("\n"),
                          ].filter(Boolean);
                          onToast?.(parts.join("\n---\n") || "filesystem hygiene", 12000);
                          return;
                        }
                        onToast?.("agent sessions arrive in slice 15", 2200);
                      }}
                    >
                      DEEPEN
                    </button>
                  </div>
                </article>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
