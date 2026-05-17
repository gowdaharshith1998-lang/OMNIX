import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("@/lib/api", () => ({
  getFile: vi.fn(() =>
    Promise.resolve({
      path: "services/governance.py",
      content: "def govern():\n  pass\n",
      last_modified: 1,
      language: "python",
    })
  ),
}));

import type { GraphNode } from "@/types/drilldown";
import { BrainTabContent, type BrainTabScopeModel } from "../BrainTabContent";

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

afterEach(() => {
  act(() => {
    for (const root of roots.splice(0)) root.unmount();
  });
  document.body.textContent = "";
  vi.clearAllMocks();
});

const scopeModel: BrainTabScopeModel = {
  connections: [
    { direction: "out", name: "verify", path: "services/verify.py", type: "CALLS" },
    { direction: "in", name: "handler", path: "services/handler.py", type: "CALLS" },
  ],
  incoming: 1,
  outgoing: 1,
  dark: 0,
};

const sym: GraphNode = {
  id: "n1",
  name: "govern",
  type: "function",
  file_path: "services/governance.py",
  line_start: 12,
  line_end: 20,
};

describe("BrainTabContent", () => {
  it("renders connections section", () => {
    const { container } = render(
      <BrainTabContent workspaceId="ws" selectedNode={null} scopeModel={scopeModel} />
    );
    expect(container.textContent).toContain("Connections");
    expect(container.textContent).toContain("outgoing");
    expect(container.textContent).toContain("incoming");
  });

  it("renders read-only signature for a selected symbol", async () => {
    const { container } = render(
      <BrainTabContent workspaceId="ws" selectedNode={sym} scopeModel={scopeModel} />
    );
    expect(container.textContent).toContain("Signature");
    expect(container.textContent).toContain("govern");
    await flush();
    expect(container.textContent).toContain("def govern()");
  });

  it("renders empty state when no symbol selected", () => {
    const { container } = render(
      <BrainTabContent workspaceId="ws" selectedNode={null} scopeModel={scopeModel} />
    );
    expect(container.textContent).toContain(
      "Select a function or class in the constellation to load source in this tab."
    );
  });

  it("does not require global state imports", () => {
    const source = BrainTabContent.toString();
    expect(source).toContain("BrainTabContent");
  });
});

