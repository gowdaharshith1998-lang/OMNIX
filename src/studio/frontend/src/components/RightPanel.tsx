import type { ReactNode } from "react";

export type RightPanelTabId = "xray" | "code" | "history" | `agent:${string}`;

export type RightPanelTab = {
  id: RightPanelTabId;
  label: string;
  closeable?: boolean;
  content: ReactNode;
};

type Props = {
  tabs: RightPanelTab[];
  activeTab: RightPanelTabId;
  onSelectTab: (tab: RightPanelTabId) => void;
  onCloseTab?: (tab: RightPanelTabId) => void;
  onNewAgentTab?: () => void;
};

export function RightPanel({
  tabs,
  activeTab,
  onSelectTab,
  onCloseTab,
  onNewAgentTab,
}: Props) {
  const active = tabs.find((tab) => tab.id === activeTab) ?? tabs[0];

  return (
    <aside className="omnix-right-panel" aria-label="OMNIX right panel">
      <div className="omnix-tab-strip" role="tablist" aria-label="Right panel tabs">
        {tabs.map((tab) => {
          const selected = tab.id === active?.id;
          return (
            <div
              key={tab.id}
              className={`omnix-tab ${selected ? "is-active" : ""}`}
              role="presentation"
            >
              <button
                type="button"
                className="omnix-tab-main"
                role="tab"
                aria-selected={selected}
                onClick={() => onSelectTab(tab.id)}
              >
                {tab.label}
              </button>
              {tab.closeable && (
                <button
                  type="button"
                  className="omnix-tab-close"
                  aria-label={`Close ${tab.label}`}
                  onClick={() => onCloseTab?.(tab.id)}
                >
                  x
                </button>
              )}
            </div>
          );
        })}
        <button
          type="button"
          className="omnix-tab-new"
          onClick={onNewAgentTab}
          aria-label="New agent tab"
          title="Agent tabs land in slice 15"
        >
          + new
        </button>
      </div>
      <div className="omnix-right-panel-body">
        {active?.content ?? (
          <div className="p-4 text-sm text-omnix-text-dim">No tab selected.</div>
        )}
      </div>
    </aside>
  );
}
