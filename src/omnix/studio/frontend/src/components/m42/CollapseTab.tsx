import type { CSSProperties } from "react";

type Props = {
  edge: "left" | "right";
  collapsed: boolean;
  onToggle: () => void;
  label?: string;
  style?: CSSProperties;
};

export function CollapseTab({ edge, collapsed, onToggle, label, style }: Props) {
  const expanded = !collapsed;
  const chevron =
    edge === "left" ? (expanded ? "‹" : "›") : expanded ? "›" : "‹";
  const aria = label ?? (edge === "left" ? "Toggle left rail" : "Toggle right panel");
  return (
    <button
      type="button"
      className={`m42-collapse-tab ${edge === "left" ? "m42-left-edge" : "m42-right-edge"}`}
      onClick={onToggle}
      aria-label={aria}
      aria-pressed={expanded}
      style={style}
    >
      {chevron}
    </button>
  );
}
