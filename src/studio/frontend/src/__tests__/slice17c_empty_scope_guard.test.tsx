import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

import type { GraphEdge, GraphNode } from "@/types/drilldown";
import { resetStudioScopeForTests } from "@/store/studioScopeStore";
import type { ScopeNavigationSpec } from "@/components/Graph/StudioGraph";
import { loadAxiomFixture } from "./integration/axiomFixture";

vi.mock("@monaco-editor/react", () => ({
  default: function MockEditor(props: { value?: string }) {
    return React.createElement("textarea", {
      "aria-label": "mock monaco",
      readOnly: true,
      value: props.value ?? "",
    });
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
  getFile: vi.fn(() => Promise.resolve({ path: "", content: "", last_modified: 1 })),
  putFile: vi.fn(),
  searchWorkspace: vi.fn(() => Promise.resolve({ hits: [] })),
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

let fixture!: ReturnType<typeof loadAxiomFixture>;

beforeAll(() => {
  fixture = loadAxiomFixture();
});

vi.mock("@/components/Graph/GraphCanvas", () => ({
  GraphCanvas: React.forwardRef(function MockGraphCanvas(
    props: {
      navigationSpec: ScopeNavigationSpec;
      onViewerScope?: (p: {
        kind: "repo" | "directory" | "file";
        path?: string;
      }) => void;
      onScopeVisualEmpty?: (d: { scopePath: string; viewLevel: string } | null) => void;
      onT1GraphNodes?: (nodes: GraphNode[]) => void;
      onT1GraphEdges?: (edges: GraphEdge[]) => void;
    },
    ref: React.Ref<{ goBack: () => void; canGoBack: () => boolean }>
  ) {
    React.useEffect(() => {
      props.onT1GraphNodes?.(fixture.nodes);
      props.onT1GraphEdges?.(fixture.edges);
    }, []);

    React.useImperativeHandle(ref, () => ({
      ingestMessage: vi.fn(),
      canGoBack: () => true,
      goBack: vi.fn(() => {
        props.onScopeVisualEmpty?.(null);
        props.onViewerScope?.({ kind: "repo" });
      }),
      applyScopeNavigation: vi.fn(),
    }));

    return (
      <div data-testid="mock-graph">
        <button
          type="button"
          data-testid="trigger-empty"
          onClick={() =>
            props.onScopeVisualEmpty?.({
              scopePath: "empty/test/dir",
              viewLevel: "star",
            })
          }
        >
          empty
        </button>
      </div>
    );
  }),
}));

import { Workspace } from "@/components/Workspace";

afterEach(() => {
  document.body.textContent = "";
  resetStudioScopeForTests();
});

beforeEach(() => {
  resetStudioScopeForTests();
});

describe("slice17c empty scope guard", () => {
  it("shows EmptyScopeState when engine reports zero visible nodes", async () => {
    const container = document.createElement("div");
    container.style.height = "800px";
    container.style.width = "1200px";
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <Workspace
          workspaceId="ws"
          projectPath="/proj"
          initialStats={{
            files: fixture.statsRepo.files,
            functions: fixture.statsRepo.functions,
            classes: fixture.statsRepo.classes,
            edges: fixture.statsRepo.edges,
          }}
          onBack={() => undefined}
        />
      );
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });

    await act(async () => {
      container
        .querySelector('[data-testid="trigger-empty"]')!
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    await act(async () => {
      expect(container.querySelector('[data-testid="empty-scope-state"]')).toBeTruthy();
      expect(container.querySelector('[data-testid="empty-scope-path"]')?.textContent).toContain(
        "empty/test/dir"
      );
    });

    await act(async () => {
      container
        .querySelector<HTMLButtonElement>('[data-testid="empty-scope-back"]')!
        .click();
    });

    await act(async () => {
      expect(container.querySelector('[data-testid="empty-scope-state"]')).toBeNull();
    });

    await act(async () => {
      root.unmount();
    });
  });
});
