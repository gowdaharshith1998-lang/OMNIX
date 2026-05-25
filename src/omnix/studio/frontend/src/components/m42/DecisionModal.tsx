import { useEffect, useState } from "react";
import type { DecisionPayload } from "./types";

type Props = {
  open: boolean;
  payload: DecisionPayload | null;
  onContinue: (selection: { optionId: string; custom?: string }) => void;
  onSkip: () => void;
  onClose: () => void;
};

export function DecisionModal({ open, payload, onContinue, onSkip, onClose }: Props) {
  const [selected, setSelected] = useState<string | null>(null);
  const [custom, setCustom] = useState("");

  useEffect(() => {
    if (!open || !payload) {
      setSelected(null);
      setCustom("");
      return;
    }
    const recommended = payload.options.find((o) => o.recommended);
    setSelected(recommended?.id ?? payload.options[0]?.id ?? null);
  }, [open, payload]);

  useEffect(() => {
    if (!open) return;
    const esc = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", esc);
    return () => window.removeEventListener("keydown", esc);
  }, [onClose, open]);

  if (!open || !payload) return null;

  const submit = () => {
    if (selected === "__custom__") {
      const text = custom.trim();
      if (!text) return;
      onContinue({ optionId: "__custom__", custom: text });
      return;
    }
    if (!selected) return;
    onContinue({ optionId: selected });
  };

  return (
    <div className="m42-modal-overlay" role="dialog" aria-modal="true" aria-labelledby="m42-decision-title">
      <div className="m42-modal">
        <div className="m42-modal-head">
          <span aria-hidden style={{ fontSize: 14 }}>⚠</span>
          <span id="m42-decision-title" className="m42-modal-head-title">
            Decision needed
          </span>
          <span className="m42-modal-head-gate">{payload.gate}</span>
        </div>
        <div className="m42-modal-body">
          <p className="m42-modal-question">
            <span
              style={{
                fontFamily: "var(--omnix-font-mono)",
                background: "var(--m42-bg-2)",
                border: "0.5px solid var(--m42-border)",
                borderRadius: 3,
                padding: "1px 6px",
                marginRight: 6,
                color: "var(--m42-text-primary)",
              }}
            >
              {payload.symbol}
            </span>
            {payload.question}
          </p>
          {payload.options.map((option) => {
            const isSelected = selected === option.id;
            return (
              <button
                key={option.id}
                type="button"
                className={`m42-modal-option ${option.recommended ? "is-recommended" : ""} ${isSelected ? "is-selected" : ""}`}
                onClick={() => setSelected(option.id)}
              >
                <span className="m42-modal-option-radio" aria-hidden />
                <span className="m42-modal-option-body">
                  <span className="m42-modal-option-title">
                    {option.title}
                    {option.recommended ? (
                      <span className="m42-modal-option-recommended-tag">recommended</span>
                    ) : null}
                  </span>
                  {option.hint ? (
                    <span className="m42-modal-option-hint">{option.hint}</span>
                  ) : null}
                </span>
              </button>
            );
          })}
          <button
            type="button"
            className={`m42-modal-option ${selected === "__custom__" ? "is-selected" : ""}`}
            onClick={() => setSelected("__custom__")}
            style={{ alignItems: "flex-start" }}
          >
            <span className="m42-modal-option-radio" aria-hidden />
            <span className="m42-modal-option-body" style={{ width: "100%" }}>
              <span className="m42-modal-option-title">Custom answer</span>
              <span className="m42-modal-custom" onClick={(event) => event.stopPropagation()}>
                <textarea
                  value={custom}
                  onChange={(event) => setCustom(event.target.value)}
                  placeholder="Describe what you want the agent to do…"
                  onFocus={() => setSelected("__custom__")}
                  aria-label="Custom answer"
                />
              </span>
            </span>
          </button>
        </div>
        <div className="m42-modal-foot">
          <button type="button" className="m42-btn is-ghost" onClick={onSkip}>
            Skip for now
          </button>
          <button
            type="button"
            className="m42-btn is-primary"
            onClick={submit}
            disabled={
              !selected || (selected === "__custom__" && custom.trim().length === 0)
            }
          >
            Continue
          </button>
        </div>
      </div>
    </div>
  );
}
