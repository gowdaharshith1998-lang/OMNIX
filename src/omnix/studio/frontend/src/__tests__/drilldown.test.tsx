import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

import type { GraphNode } from "@/types/drilldown";
import {
  getStudioScopeSnapshot,
  resetStudioScopeForTests,
} from "@/store/studioScopeStore";

const HYB_FN_ID =
  "apps/backend/src/omnix/axiom/services/crypto/hybrid_signer.py::verify_hybrid";

const FIXTURE_NODES: GraphNode[] = [
  {
    id: HYB_FN_ID,
    name: "verify_hybrid",
    type: "function",
    file_path: "apps/backend/src/omnix/axiom/services/crypto/hybrid_signer.py",
    line_start: 10,
    line_end: 42,
  },
];

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
  getFile: vi.fn(() =>
    Promise.resolve({
      path: "apps/backend/src/omnix/axiom/services/crypto/hybrid_signer.py",
      content: "def verify_hybrid():\n    return True\n",
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

vi.mock("../components/Graph/GraphCanvas", () => ({
  GraphCanvas: React.forwardRef(function MockGraphCanvas(
    props: {
      navigationSpec?: { kind: string; path?: string };
      onViewerScope?: (p: {
        kind: "repo" | "directory" | "file";
        path?: string;
      }) => void;
      onFunctionNodeClick?: (id: string) => void;
      onT1GraphNodes?: (nodes: GraphNode[]) => void;
      onT1GraphEdges?: (edges: unknown[]) => void;
    },
    ref: React.Ref<{
      applyScopeNavigation: (s: unknown) => void;
      ingestMessage: (m: unknown) => void;
      canGoBack: () => boolean;
      goBack: () => void;
      simulateRenderError?: () => void;
    }>
  ) {
    React.useImperativeHandle(ref, () => ({
      ingestMessage: vi.fn(),
      canGoBack: () => false,
      goBack: vi.fn(),
      applyScopeNavigation: vi.fn(),
      simulateRenderError: vi.fn(),
    }));
    React.useEffect(() => {
      props.onT1GraphNodes?.(FIXTURE_NODES);
      props.onT1GraphEdges?.([]);
      // One-shot fixture seed; deps must not be `props` (new reference every render → infinite loop).
    }, []);
    return (
      <div data-testid="mock-graph">
        <button
          type="button"
          aria-label="AXIOM-V2 galaxy"
          onClick={() =>
            props.onViewerScope?.({
              kind: "directory",
              path: "apps/backend/src/omnix/axiom",
            })
          }
        >
          AXIOM-V2
        </button>
        <button
          type="button"
          data-testid="go-crypto"
          onClick={() =>
            props.onViewerScope?.({
              kind: "directory",
              path: "apps/backend/src/omnix/axiom/services/crypto",
            })
          }
        >
          crypto
        </button>
        <button
          type="button"
          data-testid="pick-fn"
          onClick={() => props.onFunctionNodeClick?.(HYB_FN_ID)}
        >
          verify_hybrid
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

async function renderWorkspace() {
  const container = document.createElement("div");
  container.style.height = "900px";
  container.style.width = "1200px";
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <Workspace
        workspaceId="ws-drill"
        projectPath="/tmp/OMNIX"
        initialStats={{ files: 2, functions: 2, classes: 0, edges: 1 }}
        onBack={() => undefined}
      />
    );
  });
  return { root, container };
}

describe("drill-down integration", () => {
  it("galaxy click sets scope av2 and X-Ray header shows AXIOM-V2", async () => {
    const { root, container } = await renderWorkspace();
    const galaxy = container.querySelector('[aria-label="AXIOM-V2 galaxy"]');
    expect(galaxy).toBeTruthy();
    await act(async () => {
      (galaxy as HTMLButtonElement).click();
    });
    expect(getStudioScopeSnapshot().currentScope).toBe("av2");
    const badge = container.querySelector('[data-testid="xray-badge"]');
    const title = container.querySelector('[data-testid="xray-name"]');
    expect(badge?.textContent).toContain("MODULE");
    expect(title?.textContent).toContain("AXIOM-V2");
    await act(async () => {
      root.unmount();
    });
  });

  it("breadcrumb OMNIX returns scope to repo after drilling to crypto", async () => {
    const { root, container } = await renderWorkspace();
    await act(async () => {
      container.querySelector<HTMLButtonElement>("[data-testid=\"go-crypto\"]")!.click();
    });
    expect(getStudioScopeSnapshot().currentScope).toBe("crypto");
    const omnix = [...container.querySelectorAll("button")].find(
      (b) => b.textContent?.trim() === "OMNIX"
    );
    expect(omnix).toBeTruthy();
    await act(async () => {
      (omnix as HTMLButtonElement).click();
    });
    expect(getStudioScopeSnapshot().currentScope).toBe("repo");
    await act(async () => {
      root.unmount();
    });
  });

  it("leaf verify_hybrid shows FUNCTION eyebrow and Brain tab shows non-empty source", async () => {
    const { root, container } = await renderWorkspace();
    await act(async () => {
      container.querySelector<HTMLButtonElement>("[data-testid=\"go-crypto\"]")!.click();
    });
    await act(async () => {
      container.querySelector<HTMLButtonElement>("[data-testid=\"pick-fn\"]")!.click();
    });
    const badge = container.querySelector('[data-testid="xray-badge"]');
    expect(badge?.textContent?.toUpperCase()).toContain("FUNCTION");
    await act(async () => {
      const tabs = [...container.querySelectorAll(".xray-itabs [role='tab']")];
      const brainBtn = tabs.find((t) => t.textContent?.trim().toUpperCase() === "BRAIN");
      expect(brainBtn).toBeTruthy();
      (brainBtn as HTMLButtonElement).click();
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    const body = container.querySelector('[data-testid="xray-code-body"]');
    expect(body?.textContent ?? "").toMatch(/verify_hybrid|def /);
    await act(async () => {
      root.unmount();
    });
  });

  it("no partial X-Ray copy after drilling to av2 — panel text omits Repository header title", async () => {
    const { root, container } = await renderWorkspace();
    await act(async () => {
      container.querySelector('[aria-label="AXIOM-V2 galaxy"]')!.dispatchEvent(
        new MouseEvent("click", { bubbles: true })
      );
    });
    const panel = container.querySelector(".xray-tab");
    expect(panel).toBeTruthy();
    expect(panel!.textContent).not.toContain("Repository");
    await act(async () => {
      root.unmount();
    });
  });
});
