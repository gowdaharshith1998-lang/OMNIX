/** Slice 18a-lite — first-load bootstrap UX (visible overlay, pointer-events-none). */

export type BootstrapOverlayPhase = "shown" | "hiding" | "hidden";

type Props = {
  phase: BootstrapOverlayPhase;
  /** When set, shown as N in "Building graph from N files"; otherwise fallback copy. */
  fileCount: number | null;
  /** Opacity transition when hiding (Tailwind duration-*). */
  hideFadeClassName?: string;
};

export function BootstrapOverlay({
  phase,
  fileCount,
  hideFadeClassName = "duration-[280ms]",
}: Props) {
  if (phase === "hidden") return null;

  const hiding = phase === "hiding";
  const body =
    fileCount != null && fileCount > 0
      ? `Building graph from ${fileCount} files…`
      : "Building graph from your workspace…";

  return (
    <div
      data-omnix-bootstrap-overlay
      className={
        "pointer-events-none fixed inset-0 z-[34] flex items-center justify-center bg-[rgba(2,6,21,0.35)] backdrop-blur-[1px] transition-opacity ease-out " +
        hideFadeClassName +
        (hiding ? " opacity-0" : " opacity-100")
      }
      aria-live="polite"
      aria-busy={phase === "shown" ? "true" : undefined}
    >
      <div className="pointer-events-none flex max-w-[min(90vw,24rem)] flex-col items-center gap-3 rounded-lg border border-omnix-accent-indigo/30 bg-[rgba(2,6,21,0.92)] px-6 py-4 text-center shadow-xl">
        <span
          className="inline-block h-2.5 w-2.5 animate-pulse rounded-full bg-omnix-accent-indigo"
          aria-hidden
        />
        <p className="select-none font-mono text-[11px] font-medium lowercase tracking-[0.12em] text-omnix-accent-indigo">
          {body}
        </p>
      </div>
    </div>
  );
}
