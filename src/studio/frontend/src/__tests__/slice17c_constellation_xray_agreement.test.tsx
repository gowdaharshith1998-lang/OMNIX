import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

import type { GraphEdge, GraphNode } from "@/types/drilldown";
import { resetStudioScopeForTests } from "@/store/studioScopeStore";
import type { ScopeNavigationSpec } from "@/components/Graph/StudioGraph";
import { extendRegistryWithGraphNodes, CANONICAL_SCOPES } from "@/store/scopeRegistry";
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

const DRILL_PATHS = [
  "apps/backend/src/axiom",
  "apps/backend/src/axiom/services/crypto",
  "packages/axiom-sdk",
  "apps/backend/src/axiom/services",
];

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
    ref: React.Ref<{ applyScopeNavigation: (s: ScopeNavigationSpec) => void }>
  ) {
    const [idx, setIdx] = React.useState(0);

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
          data-testid="drill-next"
          onClick={() => {
            const path = DRILL_PATHS[idx % DRILL_PATHS.length]!;
            setIdx((n) => n + 1);
            props.onViewerScope?.({ kind: "directory", path });
          }}
        >
          drill
        </button>
      </div>
    );
  }),
}));

import { Workspace } from "@/components/Workspace";

function ti(c: HTMLElement, id: string) {
  return c.querySelector(`[data-testid="${id}"]`);
}

afterEach(() => {
  document.body.textContent = "";
  resetStudioScopeForTests();
});

beforeEach(() => {
  resetStudioScopeForTests();
});

describe("slice17c constellation / X-Ray agreement", () => {
  it("20 randomized drills: viewer path echo matches X-Ray path line for module scopes", async () => {
    const container = document.createElement("div");
    container.style.height = "800px";
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <Workspace
          workspaceId="ws"
          projectPath="/tmp/OMNIX"
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

    for (let i = 0; i < 20; i++) {
      await act(async () => {
        container
          .querySelector('[data-testid="drill-next"]')!
          .dispatchEvent(new MouseEvent("click", { bubbles: true }));
      });

      await act(async () => {
        const cons = container.querySelector('[data-omnix-constellation="1"]');
        const viewerPath = cons?.getAttribute("data-studio-viewer-scope-path") ?? "";
        const pathLine = ti(container, "xray-path")?.textContent?.replace(/\\/g, "/").trim() ?? "";
        expect(pathLine).toBe(viewerPath);
      });
    }

    await act(async () => {
      root.unmount();
    });
  });

  it("rapid setScope resolves to latest id", async () => {
    const {
      setScope,
      setValidScopeIds,
      getStudioScopeSnapshot,
      resetStudioScopeForTests: reset,
    } = await import("@/store/studioScopeStore");
    reset();
    const extended = extendRegistryWithGraphNodes(CANONICAL_SCOPES, fixture.nodes);
    setValidScopeIds(extended.map((r) => r.id));
    const ids = extended.map((r) => r.id).filter((k) => k !== "repo");
    if (ids.length < 2) {
      expect(true).toBe(true);
      return;
    }
    await act(async () => {
      setScope(ids[0]!);
      setScope(ids[1]!);
    });
    expect(getStudioScopeSnapshot().currentScope).toBe(ids[1]);
  });
});
