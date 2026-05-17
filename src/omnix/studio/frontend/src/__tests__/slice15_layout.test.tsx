import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

vi.mock("@/lib/ws", () => ({
  StudioWebSocket: vi.fn().mockImplementation(function MockWs() {
    return { connect: vi.fn(), close: vi.fn() };
  }),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    listFiles: vi.fn(() => Promise.resolve([])),
    listReceipts: vi.fn(() => Promise.resolve([])),
    getStudioInitial: vi.fn(() => Promise.resolve({ path: "" })),
    openWorkspace: vi.fn(),
  };
});

vi.mock("../components/Graph/GraphCanvas", () => ({
  GraphCanvas: React.forwardRef(function MockGraphCanvas(
    _props: unknown,
    ref: React.Ref<{ applyScopeNavigation: () => void }>
  ) {
    React.useImperativeHandle(ref, () => ({
      ingestMessage: vi.fn(),
      canGoBack: () => false,
      goBack: vi.fn(),
      applyScopeNavigation: vi.fn(),
      simulateRenderError: vi.fn(),
    }));
    return (
      <div data-testid="mock-graph" className="absolute inset-0">
        <div data-omnix-brain-root="1" className="relative h-full w-full">
          <div data-testid="layout-probe-stats" />
        </div>
      </div>
    );
  }),
}));

import { Workspace } from "@/components/Workspace";

afterEach(() => {
  document.body.textContent = "";
  vi.unstubAllGlobals();
});

beforeEach(() => {
  vi.stubGlobal("innerWidth", 1920);
  vi.stubGlobal("innerHeight", 1200);
});

describe("slice15 layout", () => {
  it("right panel width at 1920px viewport is clamped between 280 and 360 inclusive", async () => {
    const container = document.createElement("div");
    container.style.height = "1200px";
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <Workspace
          workspaceId="ws-layout"
          projectPath="/tmp/OMNIX"
          initialStats={{ files: 1, functions: 1, classes: 0, edges: 0 }}
          onBack={() => undefined}
        />
      );
    });
    const aside = container.querySelector(".omnix-right-panel") as HTMLElement | null;
    expect(aside).toBeTruthy();
    const raw = aside!.style.getPropertyValue("--right-panel-width").trim();
    const px = Number.parseInt(raw, 10);
    expect(px).toBeGreaterThanOrEqual(280);
    expect(px).toBeLessThanOrEqual(360);
    await act(async () => {
      root.unmount();
    });
  });

  it("stats card lives inside constellation container, not inside right panel", async () => {
    const container = document.createElement("div");
    container.style.height = "900px";
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <Workspace
          workspaceId="ws-layout2"
          projectPath="/tmp/OMNIX"
          initialStats={{ files: 1, functions: 1, classes: 0, edges: 0 }}
          onBack={() => undefined}
        />
      );
    });
    const right = container.querySelector(".omnix-right-panel");
    const stats = container.querySelector('[data-omnix-stats-card="1"]') as HTMLElement | null;
    expect(stats).toBeTruthy();
    expect(right?.contains(stats)).toBe(false);
    const graphHost = stats!.closest("[data-omnix-brain=\"1\"]");
    expect(graphHost).toBeTruthy();
    expect(stats!.className.split(/\s+/).includes("absolute")).toBe(true);
    await act(async () => {
      root.unmount();
    });
  });

  it("find bar is centered at bottom of constellation region", async () => {
    const container = document.createElement("div");
    container.style.height = "900px";
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <Workspace
          workspaceId="ws-layout3"
          projectPath="/tmp/OMNIX"
          initialStats={{ files: 1, functions: 1, classes: 0, edges: 0 }}
          onBack={() => undefined}
        />
      );
    });
    const findHost = container.querySelector('[data-omnix-find-slot="1"]') as HTMLElement | null;
    expect(findHost).toBeTruthy();
    const shell = findHost!.closest("[data-omnix-brain=\"1\"]");
    expect(shell).toBeTruthy();
    expect(findHost!.className.split(/\s+/).includes("absolute")).toBe(true);
    expect(findHost!.className).toContain("left-1/2");
    expect(findHost!.className).toContain("-translate-x-1/2");
    expect(findHost!.className).toContain("bottom-[50px]");
    await act(async () => {
      root.unmount();
    });
  });
});
