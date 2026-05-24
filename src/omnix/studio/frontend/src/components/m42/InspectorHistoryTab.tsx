import type { WireEvent } from "@/components/inspector/AgentTab";

type Props = {
  events: WireEvent[];
};

function ts(ms: number) {
  const date = new Date(ms);
  if (Number.isNaN(date.getTime())) return "--:--:--";
  return date.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  });
}

function colorForType(t: string): string {
  switch (t) {
    case "node_added":
      return "var(--m42-status-success)";
    case "node_modified":
      return "var(--m42-status-warning)";
    case "node_removed":
      return "var(--m42-status-danger)";
    case "edge_added":
    case "edge_removed":
      return "var(--m42-text-tertiary)";
    default:
      return "var(--m42-text-tertiary)";
  }
}

export function InspectorHistoryTab({ events }: Props) {
  if (events.length === 0) {
    return (
      <div style={{ padding: 16 }}>
        <div
          className="m42-xray-card"
          style={{ color: "var(--m42-text-tertiary)" }}
        >
          No timeline events yet — they appear as the agent makes changes.
        </div>
      </div>
    );
  }
  return (
    <div
      style={{
        padding: 12,
        display: "flex",
        flexDirection: "column",
        gap: 4,
        overflowY: "auto",
        height: "100%",
      }}
    >
      {events.map((e) => (
        <div
          key={e.id}
          style={{
            padding: "6px 10px",
            borderLeft: `2px solid ${colorForType(e.type)}`,
            background: "var(--m42-bg-1)",
            borderRadius: 2,
            fontFamily: "var(--omnix-font-mono)",
            fontSize: 11,
            color: "var(--m42-text-primary)",
            display: "flex",
            justifyContent: "space-between",
            gap: 8,
          }}
          data-event-type={e.type}
        >
          <span style={{ minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
            <span style={{ color: "var(--m42-text-tertiary)" }}>{e.type}</span>{" "}
            <span>{e.targetId}</span>
          </span>
          <span style={{ color: "var(--m42-text-tertiary)" }}>{ts(e.ts)}</span>
        </div>
      ))}
    </div>
  );
}
