import { useCallback, useEffect, useState } from "react";

const btnClass =
  "shrink-0 cursor-pointer rounded-lg border font-sans text-xs font-medium transition-all " +
  "border-[--omnix-bottom-btn-border] bg-[--omnix-bottom-btn-bg] text-slate-300 " +
  "px-3.5 py-2 " +
  "hover:border-omnix-accent-indigo hover:text-white hover:shadow-omnix-glow";

const btnDim = `${btnClass} border-[rgba(99,102,241,0.2)] opacity-50 hover:opacity-100`;

type Props = {
  onExportJson: () => void;
  onDarkMatter: () => void;
  onTimeline: () => void;
};

export function BottomToolbar({ onExportJson, onDarkMatter, onTimeline }: Props) {
  const [fs, setFs] = useState(!!document.fullscreenElement);
  useEffect(() => {
    const s = () => setFs(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", s);
    return () => document.removeEventListener("fullscreenchange", s);
  }, []);
  const onFull = useCallback(() => {
    if (!document.fullscreenElement) {
      void document.documentElement.requestFullscreen();
    } else {
      void document.exitFullscreen();
    }
  }, []);
  return (
    <div
      className="omnix-glass flex flex-wrap items-center justify-center gap-3 border border-omnix-accent-indigo/20 px-4 py-2.5 text-xs"
      id="bottom-bar"
    >
      <span
        id="omnix-version"
        className="mr-2 font-display text-[10px] tracking-[0.15em] text-omnix-text-dim"
      >
        OMNIX V0.1
      </span>
      <button type="button" className={btnClass} onClick={onFull}>
        {fs ? "Exit fullscreen" : "Fullscreen"}
      </button>
      <button type="button" className={btnDim} onClick={onDarkMatter}>
        🌀 Dark Matter
      </button>
      <button type="button" className={btnDim} onClick={onTimeline}>
        ⏳ Timeline
      </button>
      <button type="button" className={btnClass} onClick={onExportJson}>
        Export JSON
      </button>
      <span
        id="fps-counter"
        className="ml-2 flex items-center font-mono text-[11px] text-[#4ade80]"
      >
        <span className="omnix-fps-dot" aria-hidden />
        60 FPS
      </span>
    </div>
  );
}
