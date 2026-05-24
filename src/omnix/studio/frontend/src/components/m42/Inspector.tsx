import type { ReactNode } from "react";
import { CollapseTab } from "./CollapseTab";
import { RIGHT_TAB_ORDER, type RightTabId } from "./types";

type Props = {
  activeTab: RightTabId;
  onChangeTab: (id: RightTabId) => void;
  collapsed: boolean;
  onToggleCollapsed: () => void;
  children: ReactNode;
};

export function Inspector({
  activeTab,
  onChangeTab,
  collapsed,
  onToggleCollapsed,
  children,
}: Props) {
  return (
    <>
      <aside
        className={`m42-inspector ${collapsed ? "is-collapsed" : ""}`}
        aria-label="OMNIX inspector"
        aria-hidden={collapsed}
        data-testid="m42-inspector"
      >
        <div className="m42-tabstrip" role="tablist" aria-label="Inspector tabs">
          {RIGHT_TAB_ORDER.map((tab) => (
            <button
              key={tab.id}
              type="button"
              role="tab"
              aria-selected={activeTab === tab.id}
              className={`m42-tab ${activeTab === tab.id ? "is-active" : ""}`}
              onClick={() => onChangeTab(tab.id)}
            >
              {tab.label}
            </button>
          ))}
        </div>
        <div className="m42-tab-body">{children}</div>
      </aside>
      <CollapseTab
        edge="right"
        collapsed={collapsed}
        onToggle={onToggleCollapsed}
        label={collapsed ? "Expand inspector" : "Collapse inspector"}
        style={{
          position: "fixed",
          right: collapsed ? 0 : "var(--m42-inspector-w)",
          top: "calc(50% + var(--m42-topbar-h) / 2)",
        }}
      />
    </>
  );
}
