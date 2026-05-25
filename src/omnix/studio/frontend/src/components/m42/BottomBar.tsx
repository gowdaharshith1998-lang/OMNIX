import { LanguagePicker } from "./LanguagePicker";
import { SOURCE_LANGUAGES, TARGET_LANGUAGES, type RunState } from "./types";

type Props = {
  runState: RunState;
  sourceLang: string;
  onSourceLangChange: (id: string) => void;
  targetLang: string;
  onTargetLangChange: (id: string) => void;
  onStart: () => void;
  onPause: () => void;
  onAbort: () => void;
  onSeeDecision: () => void;
  onVerifyReceipt: () => void;
  onDownloadZip: () => void;
  onDownloadPdf: () => void;
  onStartAnother: () => void;
  progressPct: number;
  etaSeconds: number | null;
  currentSymbol: string | null;
  doneSummary: string | null;
  doneReceiptHash: string | null;
};

function eta(seconds: number | null): string {
  if (seconds == null || seconds <= 0) return "—";
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  if (m > 0) return `${m}m ${s.toString().padStart(2, "0")}s`;
  return `${s}s`;
}

export function BottomBar(props: Props) {
  const { runState } = props;
  if (runState === "running") {
    return (
      <footer className="m42-bottombar" data-testid="m42-bottombar" data-state="running">
        <span className="m42-bottombar-label">running</span>
        <div className="m42-progress-track" aria-label="Progress" role="progressbar" aria-valuenow={Math.round(props.progressPct)} aria-valuemin={0} aria-valuemax={100}>
          <div
            className="m42-progress-fill"
            style={{ transform: `scaleX(${Math.min(1, Math.max(0, props.progressPct / 100))})` }}
          />
        </div>
        <span className="m42-progress-label">{Math.round(props.progressPct)}% · eta {eta(props.etaSeconds)}</span>
        {props.currentSymbol ? <span className="m42-symbol">{props.currentSymbol}</span> : null}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button type="button" className="m42-btn is-ghost" onClick={props.onPause}>Pause</button>
          <button type="button" className="m42-btn is-danger" onClick={props.onAbort}>Abort</button>
        </div>
      </footer>
    );
  }
  if (runState === "decision") {
    return (
      <footer className="m42-bottombar" data-testid="m42-bottombar" data-state="decision">
        <span className="m42-bottombar-label" style={{ color: "var(--m42-status-warning)" }}>paused</span>
        <span className="m42-progress-label">decision needed — see modal</span>
        <button type="button" className="m42-btn is-ghost" style={{ marginLeft: "auto" }} onClick={props.onSeeDecision}>
          Open decision →
        </button>
      </footer>
    );
  }
  if (runState === "done") {
    return (
      <footer className="m42-bottombar" data-testid="m42-bottombar" data-state="done">
        <span className="m42-bottombar-label" style={{ color: "var(--m42-status-success)" }}>complete</span>
        <span className="m42-progress-label">{props.doneSummary ?? "Rebuild complete."}</span>
        {props.doneReceiptHash ? (
          <span className="m42-symbol">receipt {props.doneReceiptHash}</span>
        ) : null}
        <div style={{ marginLeft: "auto", display: "flex", gap: 8 }}>
          <button type="button" className="m42-btn" onClick={props.onVerifyReceipt}>Verify</button>
          <button type="button" className="m42-btn" onClick={props.onDownloadZip}>.zip</button>
          <button type="button" className="m42-btn" onClick={props.onDownloadPdf}>PDF</button>
          <button type="button" className="m42-btn is-primary" onClick={props.onStartAnother}>Start another</button>
        </div>
      </footer>
    );
  }
  return (
    <footer className="m42-bottombar" data-testid="m42-bottombar" data-state="idle">
      <span className="m42-bottombar-label">source</span>
      <LanguagePicker
        options={SOURCE_LANGUAGES}
        value={props.sourceLang}
        onChange={props.onSourceLangChange}
        ariaLabel="Source language"
        size="sm"
      />
      <span className="m42-arrow">→</span>
      <span className="m42-bottombar-label">target</span>
      <LanguagePicker
        options={TARGET_LANGUAGES}
        value={props.targetLang}
        onChange={props.onTargetLangChange}
        ariaLabel="Target language"
      />
      <button
        type="button"
        className="m42-btn is-primary"
        style={{ marginLeft: "auto" }}
        onClick={props.onStart}
      >
        Start modernization
      </button>
    </footer>
  );
}
