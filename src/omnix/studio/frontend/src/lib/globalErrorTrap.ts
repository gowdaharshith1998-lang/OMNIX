import { logStudioError } from "@/lib/studioLogger";

export type GlobalErrorTrapOptions = {
  /** Same signature as Workspace `showToastStable` — message + optional duration. */
  onToast: (message: string, durationMs?: number) => void;
};

const DEBOUNCE_MS = 100;
const STORM_WINDOW_MS = 2000;

/**
 * Captures uncaught errors from rAF/ticker callbacks, async promises, and other
 * non-React paths. Surfaces debounced toasts so error storms do not spam the UI.
 */
export function installGlobalErrorTrap(
  options: GlobalErrorTrapOptions
): () => void {
  const { onToast } = options;

  let debounceTimer: ReturnType<typeof setTimeout> | null = null;
  let batchMsg = "";
  let batchCount = 0;
  let batchStartedAt = 0;

  const flushToast = () => {
    debounceTimer = null;
    if (!batchMsg && batchCount === 0) return;
    const text =
      batchCount > 1
        ? `${batchMsg} (×${batchCount})`
        : batchMsg || "Render error — see console";
    onToast(text, 4000);
    batchMsg = "";
    batchCount = 0;
  };

  const handleUncaught = (msg: string) => {
    const now = Date.now();
    const clean = msg.trim() || "Render error — see console";
    if (
      clean === batchMsg &&
      batchCount > 0 &&
      now - batchStartedAt < STORM_WINDOW_MS
    ) {
      batchCount += 1;
    } else {
      batchMsg = clean;
      batchCount = 1;
      batchStartedAt = now;
    }
    if (debounceTimer) clearTimeout(debounceTimer);
    debounceTimer = setTimeout(flushToast, DEBOUNCE_MS);
  };

  const previousOnError = window.onerror;
  const previousOnRejection = window.onunhandledrejection;

  window.onerror = (
    message: string | Event,
    source?: string,
    lineno?: number,
    colno?: number,
    error?: Error
  ) => {
    const msg =
      error instanceof Error
        ? error.message
        : typeof message === "string"
          ? message
          : "Render error — see console";
    logStudioError("window.onerror", msg, error);
    handleUncaught(msg);
    if (typeof previousOnError === "function") {
      return previousOnError(message, source, lineno, colno, error) as
        | boolean
        | void;
    }
    return false;
  };

  window.onunhandledrejection = (event: PromiseRejectionEvent) => {
    const reason = event.reason;
    const msg =
      reason instanceof Error ? reason.message : String(reason ?? "");
    logStudioError(
      "unhandledrejection",
      msg,
      reason instanceof Error ? reason : undefined
    );
    handleUncaught(msg);
    if (typeof previousOnRejection === "function") {
      previousOnRejection.call(window, event);
    }
  };

  return () => {
    if (debounceTimer) {
      clearTimeout(debounceTimer);
      debounceTimer = null;
    }
    batchMsg = "";
    batchCount = 0;
    window.onerror = previousOnError;
    window.onunhandledrejection = previousOnRejection;
  };
}
