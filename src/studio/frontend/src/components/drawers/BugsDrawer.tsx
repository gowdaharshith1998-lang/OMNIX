export function BugsDrawer() {
  return (
    <div className="p-4">
      <div className="mb-3 font-mono text-[10px] uppercase tracking-[0.18em] text-omnix-text-dim">
        bugs
      </div>
      <div className="rounded-lg border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.5)] p-4">
        <div className="font-display text-sm font-bold text-omnix-text-primary">
          Scan arrives in slice 14b
        </div>
        <p className="mt-2 text-sm leading-6 text-omnix-text-dim">
          This drawer is reserved for bug surfacing. The SCAN button, SBFL ranking,
          and backend wiring remain out of scope for slice 14.
        </p>
      </div>
    </div>
  );
}
