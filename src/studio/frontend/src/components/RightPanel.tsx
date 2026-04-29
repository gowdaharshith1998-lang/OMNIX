import type { CSSProperties, PointerEvent, ReactNode } from "react";
import {
  RIGHT_PANEL_MAX,
  RIGHT_PANEL_MIN,
  clampWidth,
} from "@/lib/persisted_widths";

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
  width: number;
  onSelectTab: (tab: RightPanelTabId) => void;
  onCloseTab?: (tab: RightPanelTabId) => void;
  onNewAgentTab?: () => void;
  onResizeEnd: (width: number) => void;
};

export function RightPanel({
  tabs,
  activeTab,
  width,
  onSelectTab,
  onCloseTab,
  onNewAgentTab,
  onResizeEnd,
}: Props) {
  const active = tabs.find((tab) => tab.id === activeTab) ?? tabs[0];
  const startResize = (event: PointerEvent<HTMLDivElement>) => {
    event.preventDefault();
    const pointerId = event.pointerId;
    event.currentTarget.setPointerCapture?.(pointerId);
    const calc = (clientX: number) =>
      clampWidth(window.innerWidth - clientX, RIGHT_PANEL_MIN, RIGHT_PANEL_MAX);
    const move = (moveEvent: globalThis.PointerEvent) => {
      const next = calc(moveEvent.clientX);
      document.documentElement.style.setProperty("--right-panel-width", `${next}px`);
    };
    const up = (upEvent: globalThis.PointerEvent) => {
      const next = calc(upEvent.clientX);
      document.documentElement.style.setProperty("--right-panel-width", `${next}px`);
      onResizeEnd(next);
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
      window.removeEventListener("pointercancel", up);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    window.addEventListener("pointercancel", up);
  };

  return (
    <aside
      className="omnix-right-panel"
      aria-label="OMNIX right panel"
      style={{ "--right-panel-width": `${width}px` } as CSSProperties}
    >
      <div
        className="omnix-resize-handle omnix-resize-handle-right"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize right panel"
        onPointerDown={startResize}
      />
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
