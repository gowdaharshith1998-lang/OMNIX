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
    props: { onFunctionNodeClick: (nodeId: string) => void },
    ref: React.Ref<{ ingestMessage: (msg: unknown) => void }>
  ) {
    React.useImperativeHandle(ref, () => ({ ingestMessage: vi.fn() }));
    return React.createElement(
      "button",
      { type: "button", onClick: () => props.onFunctionNodeClick("n1") },
      "graph node"
    );
  }),
}));

vi.mock("@/lib/api", () => ({
  listFiles: vi.fn(() => Promise.resolve([])),
  createFile: vi.fn(),
  listReceipts: vi.fn(() => Promise.resolve([])),
  getFileTree: vi.fn(() => Promise.resolve({ name: "proj", type: "dir", children: [] })),
  searchWorkspace: vi.fn(() => Promise.resolve([])),
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

import { Workspace } from "../Workspace";
import { XRayTab } from "../XRayTab";

function render(node: React.ReactElement): { root: Root; container: HTMLDivElement } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
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
  document.body.textContent = "";
  wsHarness.reset();
  vi.clearAllMocks();
});

describe("XRayTab", () => {
  it("renders repo-root intelligence with no selection", () => {
    const { container } = render(
      <XRayTab selectedNode={null} graphNodes={nodes} graphEdges={edges} stats={stats} onSuggestedAction={vi.fn()} />
    );
    expect(container.textContent).toContain("Repository");
    expect(container.textContent).toContain("Files");
    expect(container.textContent).toContain("HEALTH");
  });

  it("renders directory/module intelligence", () => {
    const { container } = render(
      <XRayTab selectedNode={nodes.get("dir")!} graphNodes={nodes} graphEdges={edges} stats={stats} onSuggestedAction={vi.fn()} />
    );
    expect(container.textContent).toContain("services");
    expect(container.textContent).toContain("FILES (by connections)");
    expect(container.textContent).toContain("CONNECTIONS");
  });

  it("renders symbol intelligence", () => {
    const { container } = render(
      <XRayTab selectedNode={nodes.get("n1")!} graphNodes={nodes} graphEdges={edges} stats={stats} onSuggestedAction={vi.fn()} />
    );
    expect(container.textContent).toContain("SIGNATURE");
    expect(container.textContent).toContain("govern");
    expect(container.textContent).toContain("CALLS");
  });

  it("fires no-op suggested action affordance", () => {
    const onAction = vi.fn();
    const noisyEdges = Array.from({ length: 25 }, (_, i): GraphEdge => ({
      id: `e${i}`,
      source_id: "n2",
      target_id: "n1",
      relationship: "CALLS",
    }));
    const { container } = render(
      <XRayTab selectedNode={nodes.get("n1")!} graphNodes={nodes} graphEdges={noisyEdges} stats={stats} onSuggestedAction={onAction} />
    );
    act(() => container.querySelector(".xray-issue button")?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    expect(onAction).toHaveBeenCalled();
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
    expect(container.textContent).toContain("X-RAY");
    expect(container.textContent).toContain("govern");
  });
});
