import type { ReactNode } from "react";
import { CollapseTab } from "./CollapseTab";

export type LeftRailIcon = "files" | "search" | "bugs" | "receipts" | "grammar" | "settings";

type RailItem = {
  id: LeftRailIcon;
  label: string;
  icon: ReactNode;
};

const ICONS: RailItem[] = [
  {
    id: "files",
    label: "Files",
    icon: (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M3 7.5A2.25 2.25 0 015.25 5.25h4.379a2.25 2.25 0 011.59.659l.53.53M3 7.5V18a2.25 2.25 0 002.25 2.25h13.5A2.25 2.25 0 0021 18V9.75A2.25 2.25 0 0018.75 7.5H3z" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: "search",
    label: "Search",
    icon: (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="11" cy="11" r="6.5" />
        <path d="M20 20l-3.4-3.4" strokeLinecap="round" />
      </svg>
    ),
  },
  {
    id: "bugs",
    label: "Bugs",
    icon: (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M8 7.5A4 4 0 0112 5a4 4 0 014 2.5v7A4 4 0 0112 18.5a4 4 0 01-4-4v-7zM6.75 12H4m16 0h-2.75M7.5 6.75l-2-2m11 2 2-2M7.5 17.25l-2 2m11-2 2 2" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: "receipts",
    label: "Receipts",
    icon: (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M7.5 3.75h9A1.5 1.5 0 0118 5.25v15l-3-1.5-3 1.5-3-1.5-3 1.5v-15a1.5 1.5 0 011.5-1.5zM9 8.25h6M9 11.25h6M9 14.25h3.75" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
  {
    id: "grammar",
    label: "Grammar",
    icon: (
      <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
        <path d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125z" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
    ),
  },
];

const SETTINGS_ITEM: RailItem = {
  id: "settings",
  label: "Settings",
  icon: (
    <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.5">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.9l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.9-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.6 1.7 1.7 0 0 0-1.9.3l-.1.1A2 2 0 1 1 4.1 16.7l.1-.1a1.7 1.7 0 0 0 .3-1.9 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.6-1.1 1.7 1.7 0 0 0-.3-1.9l-.1-.1A2 2 0 1 1 7.1 4.7l.1.1a1.7 1.7 0 0 0 1.9.3H9.1a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.9-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.9V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" />
    </svg>
  ),
};

type Props = {
  active: LeftRailIcon | null;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  onSelect: (icon: LeftRailIcon) => void;
};

export function LeftRail({ active, collapsed, onToggleCollapsed, onSelect }: Props) {
  return (
    <>
      <aside
        className={`m42-leftrail ${collapsed ? "is-collapsed" : ""}`}
        aria-label="OMNIX activity rail"
        data-testid="m42-leftrail"
        aria-hidden={collapsed}
      >
        {ICONS.map((item) => (
          <button
            key={item.id}
            type="button"
            className={`m42-rail-btn ${active === item.id ? "is-active" : ""}`}
            onClick={() => onSelect(item.id)}
            aria-label={item.label}
            aria-pressed={active === item.id}
            title={item.label}
          >
            {item.icon}
          </button>
        ))}
        <div className="m42-rail-spacer" />
        <button
          type="button"
          className={`m42-rail-btn ${active === SETTINGS_ITEM.id ? "is-active" : ""}`}
          onClick={() => onSelect(SETTINGS_ITEM.id)}
          aria-label={SETTINGS_ITEM.label}
          aria-pressed={active === SETTINGS_ITEM.id}
          title={SETTINGS_ITEM.label}
        >
          {SETTINGS_ITEM.icon}
        </button>
      </aside>
      <CollapseTab
        edge="left"
        collapsed={collapsed}
        onToggle={onToggleCollapsed}
        label={collapsed ? "Expand left rail" : "Collapse left rail"}
        style={{ position: "fixed", left: collapsed ? 0 : "var(--m42-leftrail-w)", top: "calc(50% + var(--m42-topbar-h) / 2)" }}
      />
    </>
  );
}
