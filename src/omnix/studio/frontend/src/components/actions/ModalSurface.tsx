import { useEffect, useRef, useState } from "react";
import { chunkText } from "@/lib/streamingChunker";
import { useActionDispatchStore, type DecisionActionModal } from "@/state/actionDispatchStore";
import { ResponseBlocks, ToolSteps } from "./ResponseBlocks";

export function ModalSurface({ modal }: { modal: DecisionActionModal }) {
  const closeModal = useActionDispatchStore((s) => s.closeModal);
  const retryModal = useActionDispatchStore((s) => s.retryModal);
  const panelRef = useRef<HTMLDivElement | null>(null);
  const [visible, setVisible] = useState("");
  const errorMessage = modal.result?.errorMessage || modal.error || "Action failed.";
  const errorClass = modal.result?.errorClass || modal.result?.error;

  useEffect(() => {
    panelRef.current?.focus();
  }, [modal.id]);

  useEffect(() => {
    if (modal.status !== "done" || !modal.result) {
      setVisible("");
      return;
    }
    const controller = new AbortController();
    void (async () => {
      for await (const chunk of chunkText(modal.result?.text ?? "", 20, 50, controller.signal)) {
        setVisible(chunk);
      }
    })();
    return () => controller.abort();
  }, [modal.result, modal.status]);

  function trapFocus(event: React.KeyboardEvent<HTMLDivElement>) {
    if (event.key === "Escape") {
      event.preventDefault();
      closeModal();
      return;
    }
    if (event.key !== "Tab") return;
    const focusable = Array.from(
      panelRef.current?.querySelectorAll<HTMLElement>(
        "button,[href],input,select,textarea,[tabindex]:not([tabindex='-1'])"
      ) ?? []
    ).filter((el) => !el.hasAttribute("disabled"));
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }

  async function apply() {
    if (!modal.result) return;
    await modal.descriptor.onApply(modal.result);
    closeModal();
  }

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 px-4"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) closeModal();
      }}
    >
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        tabIndex={-1}
        className="max-h-[82vh] w-full max-w-2xl overflow-hidden rounded-xl border border-omnix-accent-indigo/25 bg-[rgba(5,8,16,0.96)] shadow-2xl outline-none"
        onKeyDown={trapFocus}
      >
        <header className="flex items-center justify-between border-b border-omnix-accent-indigo/15 px-4 py-3">
          <h2 className="font-display text-lg font-bold text-omnix-text-primary">
            {modal.descriptor.title}
          </h2>
          <button
            type="button"
            className="rounded px-2 py-1 text-omnix-text-muted hover:text-omnix-text-primary"
            onClick={closeModal}
          >
            x
          </button>
        </header>
        <div className="max-h-[58vh] space-y-3 overflow-y-auto px-4 py-3">
          {modal.status === "loading" && (
            <p className="text-sm text-omnix-text-muted">Thinking...</p>
          )}
          {modal.status === "error" && (
            <div className="space-y-2 rounded border border-rose-400/30 bg-rose-400/5 p-2">
              <p className="text-sm text-rose-200">{errorMessage}</p>
              {errorClass && (
                <span className="inline-block rounded border border-rose-300/30 px-1.5 py-0.5 font-mono text-[10px] uppercase tracking-wide text-rose-100/80">
                  {errorClass}
                </span>
              )}
              <button
                type="button"
                className="rounded border border-rose-300/40 px-2 py-1 font-mono text-[10px] uppercase text-rose-100"
                onClick={retryModal}
              >
                Retry
              </button>
            </div>
          )}
          {modal.status === "done" && modal.result && (
            <>
              <ToolSteps
                steps={modal.result.toolSteps}
                capped={modal.result.capped}
                capReason={modal.result.capReason}
              />
              {modal.result.costCapTriggered && (
                <div className="rounded border border-amber-300/30 bg-amber-300/5 p-2 text-xs text-amber-100">
                  Tool output was capped to control cost.
                </div>
              )}
              <ResponseBlocks text={visible || modal.result.text} />
            </>
          )}
        </div>
        <footer className="flex justify-end gap-2 border-t border-omnix-accent-indigo/15 px-4 py-3">
          <button
            type="button"
            className="rounded border border-[var(--omnix-shell-border)] px-3 py-1.5 text-sm text-omnix-text-muted hover:text-omnix-text-primary"
            onClick={closeModal}
          >
            {modal.descriptor.cancelLabel}
          </button>
          <button
            type="button"
            className="rounded border border-omnix-accent-indigo/50 bg-omnix-accent-indigo/15 px-3 py-1.5 text-sm text-omnix-text-primary disabled:cursor-wait disabled:opacity-50"
            disabled={modal.status !== "done" || !modal.result}
            onClick={() => void apply()}
          >
            {modal.descriptor.applyLabel}
          </button>
        </footer>
      </div>
    </div>
  );
}
