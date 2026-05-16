import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

import { BottomToolbar } from "@/components/BottomToolbar";
import { ConstellationBoundary } from "@/components/ConstellationBoundary";
import { Welcome } from "@/components/Welcome";
import { Workspace } from "@/components/Workspace";
import {
  getStudioScopeSnapshot,
  resetStudioScopeForTests,
  setSelectedNode,
} from "@/store/studioScopeStore";

let capturedGraphOnDeselect: (() => void) | undefined;

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
    getStudioInitial: vi.fn(() => Promise.resolve({ path: "/tmp/proj" })),
    listRecent: vi.fn(() => Promise.resolve([])),
    openWorkspace: vi.fn(),
  };
});

vi.mock("../components/Graph/GraphCanvas", () => ({
  GraphCanvas: React.forwardRef(function MockGraphCanvas(
    props: { onDeselect?: () => void },
    ref: React.Ref<{ applyScopeNavigation: () => void }>
  ) {
    capturedGraphOnDeselect = props.onDeselect;
    React.useImperativeHandle(ref, () => ({
      ingestMessage: vi.fn(),
      canGoBack: () => false,
      goBack: vi.fn(),
      applyScopeNavigation: vi.fn(),
      simulateRenderError: vi.fn(),
    }));
    return <div data-testid="mock-graph" />;
  }),
}));

afterEach(() => {
  document.body.textContent = "";
  capturedGraphOnDeselect = undefined;
  vi.unstubAllGlobals();
});

beforeEach(() => {
  vi.stubGlobal("innerWidth", 1920);
  vi.stubGlobal("innerHeight", 1200);
  resetStudioScopeForTests();
});

describe("slice 15.1 credibility sweep", () => {
  it("E7 — BottomToolbar does not render a hardcoded FPS label before the engine samples", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <BottomToolbar onExportJson={() => undefined} onDarkMatter={() => undefined} onTimeline={() => undefined} />
      );
    });
    expect(container.textContent).not.toMatch(/^\s*60\s*FPS\s*$/m);
    expect(container.querySelector("#fps-counter")).toBeNull();
    await act(async () => {
      root.unmount();
    });
  });

  it("E8 — ConstellationBoundary error UI has no Open devtools button", async () => {
    function ThrowingChild(): React.ReactNode {
      throw new Error("simulated");
    }
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <ConstellationBoundary onRetry={() => undefined}>
          <ThrowingChild />
        </ConstellationBoundary>
      );
    });
    expect(container.textContent).toMatch(/F12/i);
    const buttons = container.querySelectorAll("button");
    const labels = [...buttons].map((b) => b.textContent?.trim() ?? "");
    expect(labels.some((t) => /Open devtools/i.test(t))).toBe(false);
    await act(async () => {
      root.unmount();
    });
  });

  it("E9 — Welcome offers Open folder only (no duplicate New project)", async () => {
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(<Welcome onOpenPath={() => undefined} busy={false} />);
    });
    await act(async () => {
      await Promise.resolve();
    });
    expect(container.textContent).not.toContain("New project");
    const openBtns = [...container.querySelectorAll("button")].filter((b) =>
      (b.textContent ?? "").includes("Open folder")
    );
    expect(openBtns).toHaveLength(1);
    await act(async () => {
      root.unmount();
    });
  });

  it("H1 — Cmd+S with no code target does not show the old save stub toast", async () => {
    const container = document.createElement("div");
    container.style.height = "900px";
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <Workspace
          workspaceId="ws-cred"
          projectPath="/tmp/OMNIX"
          initialStats={{ files: 1, functions: 1, classes: 0, edges: 0 }}
          onBack={() => undefined}
        />
      );
    });
    await act(async () => {
      const ev = new KeyboardEvent("keydown", {
        key: "s",
        metaKey: true,
        bubbles: true,
        cancelable: true,
      });
      window.dispatchEvent(ev);
    });
    expect(container.textContent).not.toContain("Code tab save lands next");
    await act(async () => {
      root.unmount();
    });
  });

  it("I1 — graph onDeselect clears selected node in scope store", async () => {
    const container = document.createElement("div");
    container.style.height = "900px";
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <Workspace
          workspaceId="ws-desel"
          projectPath="/tmp/OMNIX"
          initialStats={{ files: 1, functions: 1, classes: 0, edges: 0 }}
          onBack={() => undefined}
        />
      );
    });
    expect(capturedGraphOnDeselect).toBeTypeOf("function");
    act(() => {
      setSelectedNode("some-node-id");
    });
    expect(getStudioScopeSnapshot().selectedNodeId).toBe("some-node-id");
    act(() => {
      capturedGraphOnDeselect?.();
    });
    expect(getStudioScopeSnapshot().selectedNodeId).toBeNull();
    await act(async () => {
      root.unmount();
    });
  });
});
