/**
 * CutoverModal — operator-facing UI for signed-receipt-gated traffic shift.
 *
 * Visual continuity with the M4.2 chrome (m42-modal-* classes from
 * DecisionModal). Wired to /v1/cutover/{unit}/{state,preview,shift,rollback}
 * on the Shape A FastAPI orchestrator.
 *
 * The receipt preview must load before "Confirm shift" enables; rollback
 * requires a reason; history rows link to /verify/r/{id} for offline-
 * verifiable proofs.
 */

import { useEffect, useState } from "react";
import {
  confirmShift,
  getCutoverState,
  previewShift,
  rollback,
  SNAP_POINTS,
  snapTo,
  type CutoverState,
  type ReceiptPreview,
} from "@/lib/cutoverApi";

type Props = {
  unit: string;
  onClose: () => void;
};

export function CutoverModal({ unit, onClose }: Props) {
  const [state, setState] = useState<CutoverState | null>(null);
  const [targetPct, setTargetPct] = useState<number | null>(null);
  const [preview, setPreview] = useState<ReceiptPreview | null>(null);
  const [previewing, setPreviewing] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [showRollback, setShowRollback] = useState(false);
  const [rollbackReason, setRollbackReason] = useState("");
  const [rollbackBusy, setRollbackBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getCutoverState(unit)
      .then((s) => {
        if (!cancelled) setState(s);
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e.message);
      });
    return () => {
      cancelled = true;
    };
  }, [unit]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  function onSliderChange(raw: number) {
    const snapped = snapTo(raw);
    setTargetPct(snapped);
    setPreview(null);
    setError(null);
    setPreviewing(true);
    previewShift(unit, snapped)
      .then(({ receiptPreview }) => {
        setPreview(receiptPreview);
        setPreviewing(false);
      })
      .catch((e: Error) => {
        setError(e.message);
        setPreviewing(false);
      });
  }

  async function onConfirm() {
    if (preview == null || targetPct == null) return;
    setConfirming(true);
    setError(null);
    try {
      await confirmShift(unit, targetPct, preview);
      // Refresh state after the shift commits.
      const next = await getCutoverState(unit);
      setState(next);
      setPreview(null);
      setTargetPct(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setConfirming(false);
    }
  }

  async function onRollback() {
    if (rollbackReason.trim().length === 0) return;
    setRollbackBusy(true);
    setError(null);
    try {
      await rollback(unit, rollbackReason.trim());
      const next = await getCutoverState(unit);
      setState(next);
      setShowRollback(false);
      setRollbackReason("");
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setRollbackBusy(false);
    }
  }

  return (
    <div
      className="m42-modal-overlay"
      role="dialog"
      aria-modal="true"
      aria-labelledby="m42-cutover-title"
      data-testid="cutover-modal"
    >
      <div className="m42-modal" style={{ width: 640, maxWidth: "92vw" }}>
        <div className="m42-modal-head">
          <span aria-hidden style={{ fontSize: 14 }}>⇄</span>
          <span id="m42-cutover-title" className="m42-modal-head-title">
            Cutover shift — unit: {unit}
          </span>
          <span className="m42-modal-head-gate">cutover</span>
        </div>
        <div className="m42-modal-body">
          <p className="m42-modal-question" data-testid="cutover-current-pct">
            {state == null ? (
              <span>Loading state…</span>
            ) : (
              <>
                Currently routing <b>{state.currentPct}%</b> to candidate.
              </>
            )}
          </p>

          <label
            htmlFor="m42-cutover-slider"
            style={{ display: "block", marginBottom: 4, color: "var(--m42-text-muted)" }}
          >
            Target percentage (snaps to {SNAP_POINTS.join(", ")})
          </label>
          <input
            id="m42-cutover-slider"
            data-testid="cutover-slider"
            type="range"
            min={0}
            max={100}
            step={1}
            value={targetPct ?? state?.currentPct ?? 0}
            onChange={(e) => onSliderChange(Number(e.target.value))}
            disabled={state == null || confirming}
            style={{ width: "100%", marginBottom: 12 }}
          />

          {previewing && (
            <div className="m42-mono-card" data-testid="cutover-preview-loading">
              Loading signed-receipt preview…
            </div>
          )}
          {preview && !previewing && (
            <pre
              className="m42-mono-card"
              data-testid="cutover-preview"
              style={{ maxHeight: 240, overflow: "auto", margin: 0 }}
            >
              {JSON.stringify(preview, null, 2)}
            </pre>
          )}
          {error && (
            <div
              className="m42-modal-error"
              role="alert"
              data-testid="cutover-error"
              style={{ color: "var(--m42-error)", marginTop: 8 }}
            >
              {error}
            </div>
          )}

          {/* Rollback section (collapsed by default) */}
          <div style={{ marginTop: 16 }}>
            <button
              type="button"
              className="m42-btn is-ghost"
              onClick={() => setShowRollback((v) => !v)}
              data-testid="cutover-toggle-rollback"
            >
              {showRollback ? "Cancel rollback" : "Emergency rollback…"}
            </button>
            {showRollback && (
              <div style={{ marginTop: 8 }}>
                <textarea
                  data-testid="cutover-rollback-reason"
                  value={rollbackReason}
                  onChange={(e) => setRollbackReason(e.target.value)}
                  placeholder="Why are we rolling back?"
                  rows={2}
                  style={{ width: "100%" }}
                />
                <button
                  type="button"
                  className="m42-btn is-destructive"
                  onClick={onRollback}
                  disabled={rollbackReason.trim().length === 0 || rollbackBusy}
                  data-testid="cutover-rollback-confirm"
                  style={{ marginTop: 8 }}
                >
                  {rollbackBusy ? "Rolling back…" : "Confirm rollback"}
                </button>
              </div>
            )}
          </div>

          {/* History footer */}
          {state && state.history.length > 0 && (
            <div style={{ marginTop: 20 }}>
              <h4 style={{ color: "var(--m42-text-muted)", margin: "0 0 6px" }}>
                Recent shifts
              </h4>
              <ul
                data-testid="cutover-history"
                style={{
                  listStyle: "none",
                  padding: 0,
                  margin: 0,
                  fontFamily: "var(--omnix-font-mono)",
                  fontSize: 11,
                }}
              >
                {state.history.slice(-5).map((h) => (
                  <li key={h.receiptId} style={{ padding: "2px 0" }}>
                    {new Date(h.ts * 1000).toISOString()} —{" "}
                    {h.fromPct}% → {h.toPct}% —{" "}
                    <a
                      href={h.receiptUrl}
                      target="_blank"
                      rel="noreferrer"
                      data-testid={`cutover-history-link-${h.receiptId}`}
                    >
                      {h.receiptId}
                    </a>
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
        <div className="m42-modal-foot">
          <button
            type="button"
            className="m42-btn is-ghost"
            onClick={onClose}
            data-testid="cutover-close"
          >
            Close
          </button>
          <button
            type="button"
            className="m42-btn is-primary"
            onClick={onConfirm}
            disabled={preview == null || confirming || targetPct === state?.currentPct}
            data-testid="cutover-confirm"
          >
            {confirming ? "Shifting…" : "Confirm shift"}
          </button>
        </div>
      </div>
    </div>
  );
}
