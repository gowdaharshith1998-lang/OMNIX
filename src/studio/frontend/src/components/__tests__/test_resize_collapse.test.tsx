import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import { LeftRail } from "../LeftRail";
import { RightPanel } from "../RightPanel";
import {
  LEFT_DRAWER_MAX,
  LEFT_DRAWER_MIN,
  RIGHT_PANEL_MAX,
  RIGHT_PANEL_MIN,
  loadShellLayout,
  saveShellLayout,
} from "@/lib/persisted_widths";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

if (!("PointerEvent" in window)) {
  (window as unknown as { PointerEvent: typeof MouseEvent }).PointerEvent = MouseEvent;
}

function render(node: React.ReactElement): { root: Root; container: HTMLDivElement } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(node));
  return { root, container };
}

function pointer(type: string, clientX: number) {
  return new window.PointerEvent(type, {
    bubbles: true,
    clientX,
    pointerId: 1,
  } as PointerEventInit);
}

afterEach(() => {
  document.body.textContent = "";
  localStorage.clear();
  document.documentElement.style.removeProperty("--left-drawer-width");
  document.documentElement.style.removeProperty("--right-panel-width");
});

describe("slice 14 resize and persistence", () => {
  it("persists shell layout round trip", () => {
    saveShellLayout("ws", {
      leftDrawer: { width: 333, openTab: "files" },
      rightPanel: { width: 555, collapsed: false },
    });
    expect(loadShellLayout("ws")).toEqual({
      leftDrawer: { width: 333, openTab: "files" },
      rightPanel: { width: 555, collapsed: false },
    });
  });

  it("clamps invalid persisted widths", () => {
    saveShellLayout("ws", {
      leftDrawer: { width: 999, openTab: null },
      rightPanel: { width: 1, collapsed: false },
    });
    expect(loadShellLayout("ws").leftDrawer.width).toBe(LEFT_DRAWER_MAX);
    expect(loadShellLayout("ws").rightPanel.width).toBe(RIGHT_PANEL_MIN);
  });

  it("resizes left drawer through pointer events", () => {
    const onResizeEnd = vi.fn();
    const { container } = render(
      <LeftRail active="files" drawerWidth={300} onSelect={vi.fn()} onClose={vi.fn()} onResizeEnd={onResizeEnd}>
        files
      </LeftRail>
    );
    const handle = container.querySelector(".omnix-resize-handle-left") as HTMLElement;
    act(() => handle.dispatchEvent(pointer("pointerdown", 348)));
    act(() => window.dispatchEvent(pointer("pointermove", 999)));
    expect(document.documentElement.style.getPropertyValue("--left-drawer-width")).toBe(`${LEFT_DRAWER_MAX}px`);
    act(() => window.dispatchEvent(pointer("pointerup", 10)));
    expect(onResizeEnd).toHaveBeenCalledWith(LEFT_DRAWER_MIN);
  });

  it("resizes right panel through pointer events", () => {
    const onResizeEnd = vi.fn();
    Object.defineProperty(window, "innerWidth", { configurable: true, value: 1200 });
    const { container } = render(
      <RightPanel
        tabs={[{ id: "xray", label: "X-Ray", content: <div>xray</div> }]}
        activeTab="xray"
        width={440}
        onSelectTab={vi.fn()}
        onResizeEnd={onResizeEnd}
      />
    );
    const handle = container.querySelector(".omnix-resize-handle-right") as HTMLElement;
    act(() => handle.dispatchEvent(pointer("pointerdown", 760)));
    act(() => window.dispatchEvent(pointer("pointermove", 300)));
    expect(document.documentElement.style.getPropertyValue("--right-panel-width")).toBe(`${RIGHT_PANEL_MAX}px`);
    act(() => window.dispatchEvent(pointer("pointerup", 1190)));
    expect(onResizeEnd).toHaveBeenCalledWith(RIGHT_PANEL_MIN);
  });

  it("renders right panel collapsed state", () => {
    const { container } = render(
      <RightPanel
        tabs={[{ id: "xray", label: "X-Ray", content: <div>xray</div> }]}
        activeTab="xray"
        width={440}
        collapsed
        onSelectTab={vi.fn()}
        onResizeEnd={vi.fn()}
      />
    );
    expect(container.querySelector(".omnix-right-panel")?.className).toContain("is-collapsed");
    expect(container.querySelector('[aria-label="Expand right panel"]')).not.toBeNull();
  });

  it("collapse chevron calls right panel toggle", () => {
    const onToggle = vi.fn();
    const { container } = render(
      <RightPanel
        tabs={[{ id: "xray", label: "X-Ray", content: <div>xray</div> }]}
        activeTab="xray"
        width={440}
        onSelectTab={vi.fn()}
        onResizeEnd={vi.fn()}
        onToggleCollapsed={onToggle}
      />
    );
    act(() => container.querySelector(".omnix-panel-collapse")?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(onToggle).toHaveBeenCalled();
  });

  it("floating expand handle calls right panel toggle", () => {
    const onToggle = vi.fn();
    const { container } = render(
      <RightPanel
        tabs={[{ id: "xray", label: "X-Ray", content: <div>xray</div> }]}
        activeTab="xray"
        width={440}
        collapsed
        onSelectTab={vi.fn()}
        onResizeEnd={vi.fn()}
        onToggleCollapsed={onToggle}
      />
    );
    act(() => container.querySelector(".omnix-right-expand-handle")?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(onToggle).toHaveBeenCalled();
  });

  it("persists collapsed right panel state", () => {
    saveShellLayout("ws", {
      leftDrawer: { width: 300, openTab: null },
      rightPanel: { width: 440, collapsed: true },
    });
    expect(loadShellLayout("ws").rightPanel.collapsed).toBe(true);
  });
});
