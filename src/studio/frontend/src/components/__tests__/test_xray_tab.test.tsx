import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { GraphEdge, GraphNode } from "@/types/drilldown";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const wsHarness = vi.hoisted(() => {
  let onMessage: ((msg: Record<string, unknown>) => void) | null = null;
  return {
    emit(msg: Record<string, unknown>) {
      onMessage?.(msg);
    },
    capture(cb: (msg: Record<string, unknown>) => void) {
      onMessage = cb;
    },
    reset() {
      onMessage = null;
    },
  };
});

const graphNavHarness = vi.hoisted(() => ({
  canGoBack: false,
  goBack: vi.fn(),
  reset() {
    this.canGoBack = false;
    this.goBack.mockClear();
  },
}));

vi.mock("@/lib/ws", () => ({
  StudioWebSocket: vi.fn(function StudioWebSocket(
    _workspaceId: string,
    onMessage: (msg: Record<string, unknown>) => void,
    onState?: (s: "connecting" | "open" | "closed") => void
  ) {
    wsHarness.capture(onMessage);
    return {
      connect: () => onState?.("open"),
      close: () => undefined,
    };
  }),
}));

vi.mock("@/components/Graph/GraphCanvas", () => ({
  GraphCanvas: React.forwardRef(function MockGraphCanvas(
    props: {
      navigationSpec?: { kind: string };
      onFunctionNodeClick: (nodeId: string) => void;
      onNavigationStateChange: (canGoBack: boolean) => void;
    },
    ref: React.Ref<{
      ingestMessage: (msg: unknown) => void;
      canGoBack: () => boolean;
      goBack: () => void;
      simulateRenderError?: () => void;
    }>
  ) {
    React.useImperativeHandle(ref, () => ({
      ingestMessage: vi.fn(),
      canGoBack: () => graphNavHarness.canGoBack,
      goBack: () => {
        graphNavHarness.canGoBack = false;
        graphNavHarness.goBack();
        props.onNavigationStateChange(false);
      },
      applyScopeNavigation: vi.fn(),
      simulateRenderError: vi.fn(),
    }));
    return React.createElement(
      React.Fragment,
      null,
      React.createElement(
        "button",
        { type: "button", onClick: () => props.onFunctionNodeClick("n1") },
        "graph node"
      ),
      React.createElement(
        "button",
        {
          type: "button",
          onClick: () => {
            graphNavHarness.canGoBack = true;
            props.onNavigationStateChange(true);
          },
        },
        "enter graph drill"
      )
    );
  }),
}));

vi.mock("@/lib/api", () => ({
  listFiles: vi.fn(() => Promise.resolve([])),
  createFile: vi.fn(),
  listReceipts: vi.fn(() => Promise.resolve([])),
  getFile: vi.fn(() =>
    Promise.resolve({
      path: "services/governance.py",
      content: "def govern():\n  pass\n",
      last_modified: 1,
      language: "python",
    })
  ),
  getFileTree: vi.fn(() => Promise.resolve({ name: "proj", type: "dir", children: [] })),
  searchWorkspace: vi.fn(() => Promise.resolve([])),
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

import { CANONICAL_SCOPES, scopeRecordsToMaps } from "@/store/scopeRegistry";
import { resetStudioScopeForTests, setSelectedNode } from "@/store/studioScopeStore";
import { Workspace } from "../Workspace";
import { XRayTab } from "../XRayTab";

const scopeById = scopeRecordsToMaps(CANONICAL_SCOPES).byId;

const roots: Root[] = [];

function render(node: React.ReactElement): { root: Root; container: HTMLDivElement } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  roots.push(root);
  act(() => root.render(node));
  return { root, container };
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

const nodes = new Map<string, GraphNode>([
  ["dir", { id: "dir", name: "services", type: "directory", file_path: "services", line_start: 0, line_end: 0 }],
  ["n1", { id: "n1", name: "govern", type: "function", file_path: "services/governance.py", line_start: 12, line_end: 20 }],
  ["n2", { id: "n2", name: "verify", type: "function", file_path: "services/verify.py", line_start: 4, line_end: 8 }],
]);

const edges: GraphEdge[] = [
  { id: 1, source_id: "n1", target_id: "n2", relationship: "CALLS" },
  { id: 2, source_id: "n2", target_id: "n1", relationship: "ENTANGLED" },
];

const stats = {
  files: 2,
  functions: 2,
  classes: 0,
  edges: 2,
  dark_matter: 0,
  entangled: 1,
};

afterEach(() => {
  act(() => {
    for (const root of roots.splice(0)) root.unmount();
  });
  document.body.textContent = "";
  wsHarness.reset();
  graphNavHarness.reset();
  vi.clearAllMocks();
  resetStudioScopeForTests();
});

describe("XRayTab", () => {
  it("renders repo-root intelligence with no selection", () => {
    resetStudioScopeForTests();
    const { container } = render(
      <XRayTab
        workspaceId="ws"
        scopeAtomId="repo"
        graphNodes={nodes}
        graphEdges={edges}
        stats={stats}
        scopeById={scopeById}
        projectPath="/tmp/proj"
        bugsScanFindings={[]}
        bugsScanSummary={null}
        onSuggestedAction={vi.fn()}
      />
    );
    expect(container.textContent).toContain("Workspace");
    expect(container.textContent).toContain("Scope metrics");
    expect(container.textContent?.includes("HEALTH")).toBe(false);
  });

  it("renders directory/module intelligence", () => {
    resetStudioScopeForTests();
    setSelectedNode("dir");
    const { container } = render(
      <XRayTab
        workspaceId="ws"
        scopeAtomId="repo"
        graphNodes={nodes}
        graphEdges={edges}
        stats={stats}
        scopeById={scopeById}
        projectPath="/tmp/proj"
        bugsScanFindings={[]}
        bugsScanSummary={null}
        onSuggestedAction={vi.fn()}
      />
    );
    expect(container.textContent).toContain("services");
    expect(container.textContent).toContain("Connections");
  });

  it("renders symbol intelligence", () => {
    resetStudioScopeForTests();
    setSelectedNode("n1");
    const { container } = render(
      <XRayTab
        workspaceId="ws"
        scopeAtomId="repo"
        graphNodes={nodes}
        graphEdges={edges}
        stats={stats}
        scopeById={scopeById}
        projectPath="/tmp/proj"
        bugsScanFindings={[]}
        bugsScanSummary={null}
        onSuggestedAction={vi.fn()}
      />
    );
    expect(container.textContent).toContain("Signature");
    expect(container.textContent).toContain("govern");
    expect(container.textContent).toContain("CALLS");
  });

  it("renders RECEIPTS empty state (no actions)", async () => {
    const onAction = vi.fn();
    const manyEntangled = Array.from({ length: 9 }, (_, i): GraphEdge => ({
      id: `ent-${i}`,
      source_id: "n1",
      target_id: "n2",
      relationship: "ENTANGLED",
    }));
    resetStudioScopeForTests();
    setSelectedNode("dir");
    const { container } = render(
      <XRayTab
        workspaceId="ws"
        scopeAtomId="repo"
        graphNodes={nodes}
        graphEdges={manyEntangled}
        stats={stats}
        scopeById={scopeById}
        projectPath="/tmp/proj"
        bugsScanFindings={[]}
        bugsScanSummary={null}
        onSuggestedAction={onAction}
      />
    );
    act(() => {
      const receipts = [...container.querySelectorAll(".xray-itabs [role='tab']")].find(
        (b) => b.textContent?.trim() === "RECEIPTS"
      );
      receipts?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();
    expect(container.textContent).toContain("No receipts yet");
    expect(onAction).not.toHaveBeenCalled();
  });

  it("renders RECEIPTS empty state with no graph", async () => {
    resetStudioScopeForTests();
    const { container } = render(
      <XRayTab
        workspaceId="ws"
        scopeAtomId="repo"
        graphNodes={new Map()}
        graphEdges={[]}
        stats={{ ...stats, files: 0, functions: 0, edges: 0 }}
        scopeById={scopeById}
        projectPath="/tmp/proj"
        bugsScanFindings={[]}
        bugsScanSummary={null}
        onSuggestedAction={vi.fn()}
      />
    );
    act(() => {
      const receipts = [...container.querySelectorAll(".xray-itabs [role='tab']")].find(
        (b) => b.textContent?.trim() === "RECEIPTS"
      );
      receipts?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await flush();
    expect(container.textContent).toContain("No receipts yet");
  });

  it("renders HISTORY stub (inner inspector history is no longer a redirect)", () => {
    const manyEntangled = Array.from({ length: 9 }, (_, i): GraphEdge => ({
      id: `ent-${i}`,
      source_id: "n1",
      target_id: "n2",
      relationship: "ENTANGLED",
    }));
    resetStudioScopeForTests();
    setSelectedNode("dir");
    const { container } = render(
      <XRayTab
        workspaceId="ws"
        scopeAtomId="repo"
        graphNodes={nodes}
        graphEdges={manyEntangled}
        stats={stats}
        scopeById={scopeById}
        projectPath="/tmp/proj"
        bugsScanFindings={[]}
        bugsScanSummary={null}
        onSuggestedAction={vi.fn()}
      />
    );
    act(() => {
      const history = [...container.querySelectorAll(".xray-itabs [role='tab']")].find(
        (b) => b.textContent?.trim() === "HISTORY"
      );
      history?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    expect(container.textContent).toContain("No history yet");
  });

  it("routes graph node clicks to X-Ray in Workspace", async () => {
    const { container } = render(
      <Workspace
        workspaceId="ws"
        projectPath="/tmp/proj"
        initialStats={stats}
        onBack={vi.fn()}
      />
    );
    act(() => {
      wsHarness.emit({
        type: "node_added",
        node: {
          id: "n1",
          name: "govern",
          type: "function",
          file_path: "services/governance.py",
          line_start: 12,
          line_end: 20,
        },
      });
    });
    await flush();
    const graphButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "graph node"
    );
    act(() => graphButton?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(container.textContent).toContain("BRAIN");
    expect(container.textContent).toContain("govern");
  });

  it("replaces breadcrumb with graph back button and handles Escape", async () => {
    const { container } = render(
      <Workspace workspaceId="ws" projectPath="/tmp/proj" initialStats={stats} onBack={vi.fn()} />
    );
    await flush();
    const enterDrill = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "enter graph drill"
    );
    act(() => enterDrill?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    await flush();
    expect(container.querySelector('[aria-label="Back in graph"]')).not.toBeNull();

    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true }));
    });
    await flush();

    expect(graphNavHarness.goBack).toHaveBeenCalled();
    expect(container.textContent).toContain("OMNIX");
  });

  it("auto-expands collapsed right panel on graph node click", async () => {
    localStorage.setItem(
      "omnix.shell.widths./tmp/proj",
      JSON.stringify({
        leftDrawer: { width: 300, openTab: null },
        rightPanel: { width: 440, collapsed: true },
      })
    );
    const { container } = render(
      <Workspace workspaceId="ws" projectPath="/tmp/proj" initialStats={stats} onBack={vi.fn()} />
    );
    expect(container.querySelector(".omnix-right-panel")?.className).toContain("is-collapsed");
    act(() => {
      wsHarness.emit({
        type: "node_added",
        node: {
          id: "n1",
          name: "govern",
          type: "function",
          file_path: "services/governance.py",
          line_start: 12,
          line_end: 20,
        },
      });
    });
    await flush();
    const graphButton = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "graph node"
    );
    act(() => graphButton?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(container.querySelector(".omnix-right-panel")?.className).not.toContain("is-collapsed");
  });

  it("supports Ctrl+B left drawer shortcut", async () => {
    const { container } = render(
      <Workspace workspaceId="ws" projectPath="/tmp/proj" initialStats={stats} onBack={vi.fn()} />
    );
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "b", ctrlKey: true, bubbles: true }));
    });
    await flush();
    expect(container.querySelector(".omnix-left-drawer")?.getAttribute("aria-label")).toBe("files drawer");
  });

  it("supports Ctrl+backslash right panel shortcut", async () => {
    const { container } = render(
      <Workspace workspaceId="ws" projectPath="/tmp/proj" initialStats={stats} onBack={vi.fn()} />
    );
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "\\", ctrlKey: true, bubbles: true }));
    });
    await flush();
    expect(container.querySelector(".omnix-right-panel")?.className).toContain("is-collapsed");
  });
});
