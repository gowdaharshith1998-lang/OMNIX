import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SearchDrawer } from "../SearchDrawer";
import type { GraphNode } from "@/types/drilldown";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const apiMock = vi.hoisted(() => ({
  searchWorkspace: vi.fn(),
}));

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    searchWorkspace: apiMock.searchWorkspace,
  };
});

function render(node: React.ReactElement): { root: Root; container: HTMLDivElement } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(node));
  return { root, container };
}

async function runDebounce(ms = 150) {
  await act(async () => {
    vi.advanceTimersByTime(ms);
    await Promise.resolve();
    await Promise.resolve();
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  apiMock.searchWorkspace.mockResolvedValue([
    { kind: "symbol", name: "run_handler", path: "src/app.py", line: 12, snippet: "" },
  ]);
});

afterEach(() => {
  document.body.textContent = "";
  vi.useRealTimers();
  vi.clearAllMocks();
});

describe("SearchDrawer", () => {
  it("debounces workspace search at 150ms", async () => {
    render(
      <SearchDrawer
        workspaceId="ws1"
        query="run"
        onQueryChange={vi.fn()}
        onOpenResult={vi.fn()}
      />
    );

    await runDebounce(149);
    expect(apiMock.searchWorkspace).not.toHaveBeenCalled();

    await runDebounce(1);
    expect(apiMock.searchWorkspace).toHaveBeenCalledWith("ws1", "run", "all", 50);
  });

  it("falls back to in-memory graph nodes without a workspace id", async () => {
    const nodes: GraphNode[] = [
      {
        id: "src/app.py::run_handler",
        name: "run_handler",
        type: "function",
        file_path: "src/app.py",
        line_start: 12,
        line_end: 16,
      },
    ];
    const { container } = render(
      <SearchDrawer
        workspaceId=""
        query="handler"
        fallbackNodes={nodes}
        onQueryChange={vi.fn()}
        onOpenResult={vi.fn()}
      />
    );

    await runDebounce();

    expect(apiMock.searchWorkspace).not.toHaveBeenCalled();
    expect(container.textContent).toContain("run_handler");
    expect(container.textContent).toContain("src/app.py:12");
  });

  it("clicks a result through to the constellation focus handler", async () => {
    const onOpenResult = vi.fn();
    const { container } = render(
      <SearchDrawer
        workspaceId="ws1"
        query="run"
        onQueryChange={vi.fn()}
        onOpenResult={onOpenResult}
      />
    );
    await runDebounce();

    const resultButton = Array.from(container.querySelectorAll("button")).find((button) =>
      button.textContent?.includes("run_handler")
    );
    act(() => {
      resultButton?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(onOpenResult).toHaveBeenCalledWith({
      kind: "symbol",
      name: "run_handler",
      path: "src/app.py",
      line: 12,
      snippet: "",
    });
  });
});
