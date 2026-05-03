/**
 * Global Studio keyboard policy: Esc priority, Cmd+P, Cmd+S, Cmd+N.
 * Cmd+S: CodeTab.save via ref when `drillOpen` (code target present); otherwise
 * `onCmdSWhenNoDrill` — intentionally silent (no save-page dialog; no stub toast).
 */

import { useEffect, useRef } from "react";

function isMod(e: KeyboardEvent) {
  return e.metaKey || e.ctrlKey;
}

export function useStudioKeybindings(opts: {
  drillOpen: boolean;
  onEscape: () => boolean;
  onTogglePicker: () => void;
  onToggleLeftDrawer: () => void;
  onToggleRightPanel: () => void;
  onNewFile: () => void;
  onCmdSWhenNoDrill: () => void;
  onSaveDrill: () => void;
}) {
  const ref = useRef(opts);
  ref.current = opts;
  useEffect(() => {
    const h = (e: KeyboardEvent) => {
      const o = ref.current;
      if (e.key === "Escape") {
        if (o.onEscape()) e.preventDefault();
        return;
      }
      if (!isMod(e)) return;
      const k = e.key.toLowerCase();
      if (k === "p") {
        e.preventDefault();
        o.onTogglePicker();
        return;
      }
      if (k === "b") {
        e.preventDefault();
        o.onToggleLeftDrawer();
        return;
      }
      if (e.key === "\\") {
        e.preventDefault();
        o.onToggleRightPanel();
        return;
      }
      if (k === "n") {
        e.preventDefault();
        o.onNewFile();
        return;
      }
      if (k === "s") {
        e.preventDefault();
        if (o.drillOpen) o.onSaveDrill();
        else o.onCmdSWhenNoDrill();
        return;
      }
    };
    window.addEventListener("keydown", h, true);
    return () => window.removeEventListener("keydown", h, true);
  }, []);
}
