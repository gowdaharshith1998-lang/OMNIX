/** Slice 6c — WebSocket reconnect UX (Option B: preserve + rebootstrap-in-place). */

export type ReconnectIndicatorMode =
  | "hidden"
  | "reconnecting"
  | "reconnected"
  | "reconnected-fade";

type Props = {
  mode: ReconnectIndicatorMode;
};

export function ReconnectIndicator({ mode }: Props) {
  if (mode === "hidden") return null;

  const reconnecting = mode === "reconnecting";
  const fade = mode === "reconnected-fade";
  const label = reconnecting ? "reconnecting" : "reconnected";

  return (
    <div
      className={
        "pointer-events-none fixed right-3 top-16 z-[35] flex items-center gap-2 rounded-md border border-amber-500/35 bg-[rgba(2,6,21,0.85)] px-3 py-1.5 font-mono text-[10px] font-medium uppercase tracking-[0.2em] text-amber-400 shadow-lg backdrop-blur-[2px]" +
        (reconnecting ? " text-amber-300" : "") +
        (fade ? " opacity-0 transition-opacity duration-200 ease-out" : " opacity-100")
      }
      aria-live="polite"
    >
      <span
        className={
          reconnecting ? "inline-block h-2 w-2 animate-pulse rounded-full bg-amber-400" : "inline-block h-2 w-2 rounded-full bg-amber-400"
        }
        aria-hidden
      />
      <span className="select-none">{label}</span>
    </div>
  );
}
