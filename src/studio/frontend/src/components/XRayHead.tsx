type Props = {
  badge: string;
  name: string;
  pathLine: string;
};

export function XRayHead({ badge, name, pathLine }: Props) {
  return (
    <header className="xray-header mb-3 border-b border-omnix-accent-indigo/15 pb-3">
      <div className="xray-label mb-1 font-mono text-[10px] uppercase tracking-[0.2em] text-omnix-text-dim">
        X-RAY
      </div>
      <div
        data-testid="xray-badge"
        className="xray-eyebrow mb-1 inline-block rounded border border-omnix-accent-indigo/30 px-2 py-0.5 font-mono text-[10px] uppercase tracking-wide text-omnix-accent-indigo"
      >
        {badge}
      </div>
      <h2
        data-testid="xray-name"
        className="mt-1 font-display text-lg font-semibold text-omnix-text-primary"
      >
        {name}
      </h2>
      <p
        data-testid="xray-path"
        className="mt-1 break-all font-mono text-[11px] text-omnix-text-muted"
      >
        {pathLine || "—"}
      </p>
    </header>
  );
}
