/** Slice 6d — first-load bootstrap UX (Option A: minimal overlay). */

/** Parent maps internal Workspace state to display phases (pending → shown). */
export type BootstrapIndicatorPhase = "shown" | "hiding" | "hidden";

type Props = {
  phase: BootstrapIndicatorPhase;
};

export function BootstrapIndicator({ phase }: Props) {
  if (phase === "hidden") return null;

  const hiding = phase === "hiding";

  return (
    <div
      className={
        "pointer-events-none fixed right-3 top-16 z-[35] flex items-center gap-2 rounded-md border border-omnix-accent-indigo/35 bg-[rgba(2,6,21,0.85)] px-3 py-1.5 font-mono text-[10px] font-medium tracking-[0.2em] text-omnix-accent-indigo shadow-lg backdrop-blur-[2px]" +
        (hiding ? " opacity-0 transition-opacity duration-200 ease-out" : " opacity-100")
      }
      aria-live="polite"
      aria-busy={phase === "shown" ? "true" : undefined}
    >
      <span
        className="inline-block h-2 w-2 animate-pulse rounded-full bg-omnix-accent-indigo"
        aria-hidden
      />
      <span className="select-none lowercase">loading workspace…</span>
    </div>
  );
}
