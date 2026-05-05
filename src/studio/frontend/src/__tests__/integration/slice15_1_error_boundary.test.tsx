import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

import type { GraphEdge, GraphNode } from "@/types/drilldown";
import { resetStudioScopeForTests } from "@/store/studioScopeStore";
import type { ScopeNavigationSpec } from "@/components/Graph/StudioGraph";

const navHarness = vi.hoisted(() => ({ failDirectoryNav: true }));

vi.mock("@monaco-editor/react", () => ({
  default: function MockEditor() {
    return React.createElement("textarea", { "aria-label": "mock monaco", readOnly: true });
  },
}));

vi.mock("@/lib/ws", () => ({
  StudioWebSocket: vi.fn().mockImplementation(() => ({
    connect: vi.fn(),
    close: vi.fn(),
  })),
}));

vi.mock("@/lib/api", () => ({
  createFile: vi.fn(),
  listFiles: vi.fn(() => Promise.resolve([])),
  listReceipts: vi.fn(() => Promise.resolve([])),
  getStudioInitial: vi.fn(() => Promise.resolve({ path: "" })),
  openWorkspace: vi.fn(),
  getFile: vi.fn(() =>
    Promise.resolve({ path: "", content: "", last_modified: 0, language: "txt" })
  ),
  putFile: vi.fn(),
  searchWorkspace: vi.fn(() => Promise.resolve({ hits: [] })),
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

vi.mock("@/components/Graph/GraphCanvas", () => ({
  GraphCanvas: React.forwardRef(function ErrMockGraph(
    props: {
      navigationSpec: ScopeNavigationSpec;
      onViewerScope?: (p: {
        kind: "repo" | "directory" | "file";
        path?: string;
      }) => void;
      onT1GraphNodes?: (nodes: GraphNode[]) => void;
      onT1GraphEdges?: (edges: GraphEdge[]) => void;
    },
    ref: React.Ref<{ simulateRenderError?: () => void }>
  ) {
    const [boom, setBoom] = React.useState<Error | null>(null);
    if (boom) throw boom;

    React.useEffect(() => {
      props.onT1GraphNodes?.([]);
      props.onT1GraphEdges?.([]);
    }, []);

    React.useEffect(() => {
      if (props.navigationSpec.kind !== "directory") return;
      if (navHarness.failDirectoryNav) {
        setBoom(new Error("Constellation apply failed"));
      }
    }, [props.navigationSpec]);

    React.useImperativeHandle(ref, () => ({
      ingestMessage: vi.fn(),
      canGoBack: () => false,
      goBack: vi.fn(),
      applyScopeNavigation: vi.fn(),
      simulateRenderError: vi.fn(),
    }));

    return (
      <div data-testid="mock-graph">
        <button
          type="button"
          aria-label="AXIOM-V2 galaxy"
          onClick={() =>
            props.onViewerScope?.({
              kind: "directory",
              path: "apps/backend/src/axiom",
            })
          }
        >
          AXIOM-V2
        </button>
      </div>
    );
  }),
}));

import { Workspace } from "@/components/Workspace";

function ti(container: HTMLElement, id: string): HTMLElement | null {
  return container.querySelector(`[data-testid="${id}"]`);
}

afterEach(() => {
  document.body.textContent = "";
  resetStudioScopeForTests();
  navHarness.failDirectoryNav = true;
});

describe("slice15.1 constellation error boundary", () => {
  it("keeps chrome mounted when constellation render fails", async () => {
    const container = document.createElement("div");
    container.style.width = "1300px";
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <Workspace
          workspaceId="ws-eb"
          projectPath="/tmp/OMNIX"
          initialStats={{ files: 1, functions: 1, classes: 0, edges: 0 }}
          onBack={() => undefined}
        />
      );
    });
    await act(async () => {
      await Promise.resolve();
    });

    await act(async () => {
      container
        .querySelector('[aria-label="AXIOM-V2 galaxy"]')!
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    await act(async () => {
      await Promise.resolve();
    });

    expect(container.textContent).toContain("Constellation render failed");
    const retry = [...container.querySelectorAll("button")].find(
      (b) => b.textContent?.trim() === "Retry"
    );
    expect(retry).toBeTruthy();
    expect(ti(container, "breadcrumb")).not.toBeNull();
    expect(ti(container, "find-bar")).not.toBeNull();
    expect(ti(container, "left-rail")).not.toBeNull();
    expect(ti(container, "omnix-status-bar")).not.toBeNull();

    await act(async () => {
      root.unmount();
    });
  });

  it("retry restores constellation viewport", async () => {
    const container = document.createElement("div");
    container.style.width = "1300px";
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <Workspace
          workspaceId="ws-eb2"
          projectPath="/tmp/OMNIX"
          initialStats={{ files: 1, functions: 1, classes: 0, edges: 0 }}
          onBack={() => undefined}
        />
      );
    });
    await act(async () => {
      await Promise.resolve();
    });

    await act(async () => {
      container
        .querySelector('[aria-label="AXIOM-V2 galaxy"]')!
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await act(async () => {
      await Promise.resolve();
    });

    navHarness.failDirectoryNav = false;
    const retry = [...container.querySelectorAll("button")].find(
      (b) => b.textContent?.trim() === "Retry"
    );
    await act(async () => {
      retry!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await act(async () => {
      await Promise.resolve();
    });

    expect(container.querySelector("[data-omnix-brain-fallback]")).toBeNull();
    expect(container.querySelector('[data-testid="mock-graph"]')).not.toBeNull();

    await act(async () => {
      root.unmount();
    });
  });
});

describe("slice15.1 X-Ray errors stay out of constellation boundary", () => {
  it("class error boundary around X-Ray does not toggle constellation fallback", async () => {
    class Eb extends React.Component<
      { children: React.ReactNode },
      { err: boolean }
    > {
      state = { err: false };
      static getDerivedStateFromError() {
        return { err: true };
      }
      render() {
        if (this.state.err)
          return <div data-testid="xray-local-fallback">xray busted</div>;
        return this.props.children;
      }
    }
    const Boom: React.FC = () => {
      throw new Error("xray");
    };
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <div>
          <div data-omnix-brain="1">
            <span data-omnix-graph-placeholder="1">graph ok</span>
          </div>
          <Eb>
            <Boom />
          </Eb>
        </div>
      );
    });
    expect(ti(container, "xray-local-fallback")?.textContent).toContain("xray busted");
    expect(container.querySelector("[data-omnix-brain-fallback]")).toBeNull();
    expect(container.textContent).toContain("graph ok");
    await act(async () => root.unmount());
  });
});
