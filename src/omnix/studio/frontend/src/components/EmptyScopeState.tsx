type Props = {
  scopePath: string;
  onBack: () => void;
};

export function EmptyScopeState({ scopePath, onBack }: Props) {
  const label = scopePath.trim() || "(repository root)";
  return (
    <div
      data-testid="empty-scope-state"
      className="pointer-events-auto absolute inset-0 z-[25] flex flex-col items-center justify-center gap-4 bg-[rgba(2,6,21,0.72)] px-6 text-center backdrop-blur-sm"
      role="alert"
    >
      <div className="font-display text-lg font-semibold text-omnix-text-primary">
        No nodes in this scope
      </div>
      <p className="max-w-md font-mono text-xs leading-relaxed text-omnix-text-muted">
        Nothing matched for{" "}
        <span data-testid="empty-scope-path" className="text-omnix-accent-indigo">
          {label}
        </span>
        . Try stepping back to the parent scope.
      </p>
      <button
        type="button"
        data-testid="empty-scope-back"
        className="rounded-md border border-omnix-accent-indigo/40 bg-[rgba(99,102,241,0.12)] px-4 py-2 font-mono text-xs uppercase tracking-wide text-omnix-text-primary transition hover:bg-[rgba(99,102,241,0.22)]"
        onClick={onBack}
      >
        Back to parent
      </button>
    </div>
  );
}
