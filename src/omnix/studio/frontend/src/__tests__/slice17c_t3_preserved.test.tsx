import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

import type { GraphEdge, GraphNode } from "@/types/drilldown";
import {
  getStudioScopeSnapshot,
  resetStudioScopeForTests,
} from "@/store/studioScopeStore";
import type { ScopeNavigationSpec } from "@/components/Graph/StudioGraph";
import { loadAxiomFixture } from "./integration/axiomFixture";

vi.mock("@monaco-editor/react", () => ({
  default: function MockEditor(props: { value?: string }) {
    return React.createElement("textarea", {
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
      onT1GraphNodes?: (nodes: GraphNode[]) => void;
      onT1GraphEdges?: (edges: GraphEdge[]) => void;
    },
    ref: React.Ref<{ ingestMessage: (m: unknown) => void }>
  ) {
    React.useEffect(() => {
      props.onT1GraphNodes?.(fixture.nodes);
      props.onT1GraphEdges?.(fixture.edges);
    }, []);

    React.useImperativeHandle(ref, () => ({
      ingestMessage: vi.fn(),
      canGoBack: () => false,
      goBack: vi.fn(),
      applyScopeNavigation: vi.fn(),
    }));

    return (
      <div data-testid="mock-graph">
        <button
          type="button"
          data-testid="emit-node"
          onClick={() =>
            props.onViewerScope?.({
              kind: "directory",
              path: "apps/backend/src/omnix/axiom",
            })
          }
        >
          drill
        </button>
        <button
          type="button"
          data-testid="graph-remap"
          onClick={() => {
            props.onT1GraphNodes?.([...fixture.nodes]);
            props.onT1GraphEdges?.([...fixture.edges]);
          }}
        >
          remap
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

describe("slice17c T3 preservation", () => {
  it("graph catalog refresh after drill does not clobber scope atom", async () => {
    const container = document.createElement("div");
    container.style.height = "800px";
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
        .querySelector('[data-testid="emit-node"]')!
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    const scopeAfterDrill = getStudioScopeSnapshot().currentScope;

    await act(async () => {
      container
        .querySelector('[data-testid="graph-remap"]')!
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    expect(getStudioScopeSnapshot().currentScope).toBe(scopeAfterDrill);

    await act(async () => {
      root.unmount();
    });
  });

  // 50 full Workspace renders is correctness- not timing-sensitive; under
  // parallel CPU starvation it can exceed the default 5s timeout. Give it room
  // and retry transient slowness — the no-throw + scope==="repo" assertions are
  // unchanged.
  it("mount/unmount Workspace repeatedly does not throw", { retry: 2, timeout: 30000 }, async () => {
    for (let i = 0; i < 50; i++) {
      const container = document.createElement("div");
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
        root.unmount();
      });
      container.remove();
    }
    expect(getStudioScopeSnapshot().currentScope).toBe("repo");
  });
});
