import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("@monaco-editor/react", () => ({
  default: function MockEditor(props: { value?: string }) {
    return React.createElement("textarea", {
      "aria-label": "mock monaco",
      readOnly: true,
      value: props.value ?? "",
    });
  },
}));

const wsHarness = vi.hoisted(() => {
  return {
    connectCalls: 0,
    reset() {
      this.connectCalls = 0;
    },
  };
});

vi.mock("@/lib/ws", () => ({
  StudioWebSocket: vi.fn().mockImplementation(() => ({
    connect: () => {
      wsHarness.connectCalls += 1;
    },
    close: () => undefined,
  })),
}));

vi.mock("@/lib/api", () => ({
  createFile: vi.fn(),
  listFiles: vi.fn(() => Promise.resolve([])),
  listReceipts: vi.fn(() => Promise.resolve([])),
  getStudioInitial: vi.fn(() => Promise.resolve({ path: "" })),
  openWorkspace: vi.fn(),
  getFile: vi.fn(() =>
    Promise.resolve({
      path: "services/governance.py",
      content: "def govern():\n  pass\n",
      last_modified: 1,
      language: "python",
    })
  ),
  putFile: vi.fn(),
  searchWorkspace: vi.fn(() => Promise.resolve({ hits: [] })),
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

vi.mock("@/components/Graph/GraphCanvas", () => ({
  GraphCanvas: React.forwardRef(function MockGraphCanvas(
    _props: Record<string, unknown>,
    ref: React.Ref<{
      applyScopeNavigation: (s: unknown) => void;
      ingestMessage: (m: unknown) => void;
      canGoBack: () => boolean;
      goBack: () => void;
    }>
  ) {
    React.useImperativeHandle(ref, () => ({
      ingestMessage: vi.fn(),
      canGoBack: () => false,
      goBack: vi.fn(),
      applyScopeNavigation: vi.fn(),
    }));
    return <div data-testid="mock-graph">graph</div>;
  }),
}));

import { resetStudioScopeForTests, setSelectedNode } from "@/store/studioScopeStore";
import { Workspace } from "../Workspace";

const roots: Root[] = [];

const PROPS: React.ComponentProps<typeof Workspace> = {
  workspaceId: "ws1",
  projectPath: "/tmp/proj",
  initialStats: { files: 0, functions: 0, classes: 0, edges: 0 },
  onBack: vi.fn(),
};

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
  wsHarness.reset();
  resetStudioScopeForTests();
});

describe("tab scaffold", () => {
  it("outer tab strip renders BRAIN (not X-Ray)", async () => {
    const { container } = render(<Workspace {...PROPS} />);
    await flush();
    expect(container.textContent).toContain("BRAIN");
    expect(container.textContent).not.toContain("X-Ray");
  });

  it("inner inspector tabs are 4 in correct order", async () => {
    const { container } = render(<Workspace {...PROPS} />);
    await flush();
    // Default right panel tab is the inspector; inner tab strip should be present.
    const tabs = Array.from(container.querySelectorAll(".xray-itabs [role='tab']")).map(
      (t) => (t.textContent ?? "").trim()
    );
    expect(tabs).toEqual(["BRAIN", "AGENT", "RECEIPTS", "HISTORY"]);
  });

  it("BRAIN is default-active on entity selection", async () => {
    resetStudioScopeForTests();
    setSelectedNode("n1");
    const { container } = render(<Workspace {...PROPS} />);
    await flush();
    const tabs = Array.from(container.querySelectorAll(".xray-itabs [role='tab']"));
    const active = tabs.find((t) => t.getAttribute("aria-selected") === "true");
    expect((active?.textContent ?? "").trim()).toBe("BRAIN");
  });

  it("BRAIN content unchanged post rename (regression selectors)", async () => {
    resetStudioScopeForTests();
    setSelectedNode("n1");
    const { container } = render(<Workspace {...PROPS} />);
    await flush();
    // This is the pre-slice-21 CODE tab content container; should still exist.
    expect(container.querySelector('[data-testid="xray-code-body"]')).toBeTruthy();
    expect(container.textContent).toContain("Connections");
  });

  it("AGENT tab renders empty state", async () => {
    const { container } = render(<Workspace {...PROPS} />);
    await flush();
    const tabs = Array.from(container.querySelectorAll(".xray-itabs [role='tab']"));
    const agent = tabs.find((t) => (t.textContent ?? "").trim() === "AGENT");
    expect(agent).toBeTruthy();
    act(() => agent?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    await flush();
    expect(container.textContent).toContain("Waiting for agent activity");
  });

  it("RECEIPTS tab renders empty state", async () => {
    const { container } = render(<Workspace {...PROPS} />);
    await flush();
    const tabs = Array.from(container.querySelectorAll(".xray-itabs [role='tab']"));
    const receipts = tabs.find((t) => (t.textContent ?? "").trim() === "RECEIPTS");
    expect(receipts).toBeTruthy();
    act(() => receipts?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    await flush();
    expect(container.textContent).toContain("No receipts yet");
  });

  it("HISTORY tab renders empty state", async () => {
    const { container } = render(<Workspace {...PROPS} />);
    await flush();
    const tabs = Array.from(container.querySelectorAll(".xray-itabs [role='tab']"));
    const history = tabs.find((t) => (t.textContent ?? "").trim() === "HISTORY");
    expect(history).toBeTruthy();
    act(() => history?.dispatchEvent(new MouseEvent("click", { bubbles: true })));
    await flush();
    expect(container.textContent).toContain("No history yet");
  });
});

