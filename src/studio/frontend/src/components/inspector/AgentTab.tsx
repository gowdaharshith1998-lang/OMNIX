type Props = {
  emptyMessage?: string;
};

export function AgentTab({ emptyMessage = "Waiting for agent activity…" }: Props) {
  return (
    <div className="rounded border border-omnix-accent-indigo/15 bg-[rgba(99,102,241,0.05)] px-3 py-2 font-mono text-[11px] text-omnix-text-muted">
      {emptyMessage}
    </div>
  );
}

