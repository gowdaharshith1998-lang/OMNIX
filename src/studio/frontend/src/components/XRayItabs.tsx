export type XRayInnerTab = "brain" | "agent" | "receipts" | "history";

type Props = {
  active: XRayInnerTab;
  onSelect: (t: XRayInnerTab) => void;
};

const TABS: { id: XRayInnerTab; label: string }[] = [
  { id: "brain", label: "BRAIN" },
  { id: "agent", label: "AGENT" },
  { id: "receipts", label: "RECEIPTS" },
  { id: "history", label: "HISTORY" },
];

export function XRayItabs({ active, onSelect }: Props) {
  return (
    <div
      className="xray-itabs mb-3 flex flex-wrap gap-1 border-b border-omnix-accent-indigo/15 pb-2"
      role="tablist"
      aria-label="Brain tabs"
    >
      {TABS.map((t) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          aria-selected={active === t.id}
          className={
            active === t.id
              ? "rounded-md bg-[rgba(99,102,241,0.2)] px-2.5 py-1 font-mono text-[11px] uppercase tracking-wide text-omnix-text-primary"
              : "rounded-md px-2.5 py-1 font-mono text-[11px] uppercase tracking-wide text-omnix-text-muted transition hover:bg-[rgba(99,102,241,0.08)] hover:text-omnix-text-primary"
          }
          onClick={() => onSelect(t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}
