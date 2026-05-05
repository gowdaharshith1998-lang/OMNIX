import { useMemo } from "react";
import { useWireEvents } from "@/lib/wireEventBuffer";

type Props = {
  workspaceId: string;
  selectedEntityId: string | null;
  emptyMessage?: string;
};

function dayKey(ts: number): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "Unknown";
  return d.toLocaleDateString(undefined, { month: "short", day: "2-digit", year: "numeric" });
}

function tsLabel(ts: number): string {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "--:--";
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function EntityHistoryTab({
  workspaceId,
  selectedEntityId,
  emptyMessage = "No history yet.",
}: Props) {
  const events = useWireEvents(workspaceId);

  const filtered = useMemo(() => {
    if (!selectedEntityId) return events;
    return events.filter((e) => e.targetId === selectedEntityId);
  }, [events, selectedEntityId]);

  const grouped = useMemo(() => {
    const map = new Map<string, typeof filtered>();
    for (const e of filtered) {
      const key = dayKey(e.ts);
      const list = map.get(key) ?? [];
      list.push(e);
      map.set(key, list);
    }
    return Array.from(map.entries());
  }, [filtered]);

  if (filtered.length === 0) {
    return (
      <div className="rounded border border-omnix-accent-indigo/15 bg-[rgba(99,102,241,0.05)] px-3 py-2 font-mono text-[11px] text-omnix-text-muted">
        {emptyMessage}
      </div>
    );
  }

  return (
    <div className="space-y-3">
      {grouped.map(([day, rows]) => (
        <section key={day}>
          <div
            data-history-day="1"
            className="mb-2 font-mono text-[10px] uppercase tracking-[0.18em] text-omnix-text-dim"
          >
            {day}
          </div>
          <div className="space-y-1">
            {rows.map((e) => (
              <div
                key={e.id}
                data-history-row="1"
                data-target-id={e.targetId}
                className="rounded border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.5)] px-2.5 py-2 font-mono text-[11px] text-omnix-text-primary"
              >
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0 truncate">
                    <span className="text-omnix-text-muted">{e.actor ?? "agent"}</span>{" "}
                    <span>{e.type}</span>{" "}
                    <span className="text-omnix-text-muted">{e.targetId}</span>
                  </div>
                  <span className="shrink-0 text-omnix-text-dim">{tsLabel(e.ts)}</span>
                </div>
              </div>
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

