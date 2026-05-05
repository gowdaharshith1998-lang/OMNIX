import { colorForType } from "@/components/Graph/entityPalette";

export type WireEventType =
  | "node_added"
  | "node_modified"
  | "node_removed"
  | "edge_added"
  | "edge_removed";

export type WireEvent = {
  id: string;
  type: WireEventType;
  ts: number; // epoch ms
  actor: string | null;
  targetId: string;
  /** Palette entity type (e.g. "code", "people"). Unknown → fallback color. */
  targetType: string;
  confidence: number | null;
};

type Props = {
  events: WireEvent[];
  emptyMessage?: string;
};

const VISIBLE_WINDOW = 100;

function tsLabel(ts: number) {
  const d = new Date(ts);
  if (Number.isNaN(d.getTime())) return "--:--";
  return d.toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

export function AgentTab({
  events,
  emptyMessage = "Waiting for agent activity…",
}: Props) {
  if (events.length === 0) {
    return (
      <div className="rounded border border-omnix-accent-indigo/15 bg-[rgba(99,102,241,0.05)] px-3 py-2 font-mono text-[11px] text-omnix-text-muted">
        {emptyMessage}
      </div>
    );
  }

  const visible = events.slice(0, VISIBLE_WINDOW);
  const hiddenCount = Math.max(0, events.length - visible.length);

  return (
    <div className="space-y-2">
      <div className="space-y-1">
        {visible.map((e) => (
          <div
            key={e.id}
            data-agent-feed-entry="1"
            data-event-type={e.type}
            data-target-id={e.targetId}
            data-confidence={e.confidence ?? ""}
            className="rounded border border-[var(--omnix-shell-border)] bg-[rgba(5,8,16,0.5)] px-2.5 py-2 font-mono text-[11px] text-omnix-text-primary"
            style={{ borderLeftColor: colorForType(e.targetType), borderLeftWidth: 3 }}
          >
            <div className="flex items-center justify-between gap-2">
              <div className="min-w-0 truncate">
                <span className="text-omnix-text-muted">{e.actor ?? "agent"}</span>{" "}
                <span>{e.type}</span>{" "}
                <span className="text-omnix-text-muted">{e.targetId}</span>
              </div>
              <span data-agent-ts="1" className="shrink-0 text-omnix-text-dim">
                {tsLabel(e.ts)}
              </span>
            </div>
          </div>
        ))}
      </div>
      {hiddenCount > 0 ? (
        <div className="rounded border border-omnix-accent-indigo/15 bg-[rgba(99,102,241,0.04)] px-2.5 py-2 font-mono text-[10px] text-omnix-text-dim">
          + {hiddenCount} earlier events
        </div>
      ) : null}
    </div>
  );
}

