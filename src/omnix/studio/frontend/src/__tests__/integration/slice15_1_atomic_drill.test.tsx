import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

import type { GraphEdge, GraphNode } from "@/types/drilldown";
import { resetStudioScopeForTests } from "@/store/studioScopeStore";
import type { ScopeNavigationSpec } from "@/components/Graph/StudioGraph";
import { loadAxiomFixture } from "./axiomFixture";

const HYB_FN_ID =
  "apps/backend/src/omnix/axiom/services/crypto/hybrid_signer.py::verify_hybrid";

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
      onFunctionNodeClick?: (id: string) => void;
      onT1GraphNodes?: (nodes: GraphNode[]) => void;
      onT1GraphEdges?: (edges: GraphEdge[]) => void;
    },
    ref: React.Ref<{
      applyScopeNavigation: (s: ScopeNavigationSpec) => void;
      ingestMessage: (m: unknown) => void;
      canGoBack: () => boolean;
      goBack: () => void;
      simulateRenderError?: () => void;
    }>
  ) {
    const [scene, setScene] = React.useState<"repo" | "av2" | "crypto" | "pkg">(
      "repo"
    );

    React.useEffect(() => {
      const spec = props.navigationSpec;
      if (!spec || spec.kind === "repo") setScene("repo");
      else if (spec.kind === "directory") {
        const p = spec.path.replace(/\\/g, "/");
        if (p === "apps/backend/src/omnix/axiom") setScene("av2");
        else if (p === "apps/backend/src/omnix/axiom/services/crypto") setScene("crypto");
        else if (p === "packages/axiom-sdk") setScene("pkg");
        else setScene("repo");
      }
    }, [props.navigationSpec]);

    React.useEffect(() => {
      props.onT1GraphNodes?.(fixture.nodes);
      props.onT1GraphEdges?.(fixture.edges);
    }, []);

    const nodeMarkers =
      scene === "repo"
        ? fixture.repoGalaxyDirCount
        : scene === "av2"
          ? fixture.av2ScopedNodeCount
          : scene === "crypto"
            ? fixture.cryptoScopedNodeCount
            : scene === "pkg"
              ? fixture.pkgScopedNodeCount
              : fixture.repoGalaxyDirCount;

    React.useImperativeHandle(ref, () => ({
      ingestMessage: vi.fn(),
      canGoBack: () => false,
      goBack: vi.fn(),
      applyScopeNavigation: vi.fn(),
      simulateRenderError: vi.fn(),
    }));

    return (
      <div data-testid="mock-graph">
        {Array.from({ length: nodeMarkers }, (_, i) => (
          <span key={i} data-omnix-node="1" />
        ))}
        <button
          type="button"
          aria-label="AXIOM-V2 galaxy"
          data-omnix-drill="galaxy-axiom"
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
          data-omnix-drill="cluster-crypto"
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
          data-testid="go-pkg"
          data-omnix-drill="galaxy-pkg"
          onClick={() =>
            props.onViewerScope?.({
              kind: "directory",
              path: "packages/axiom-sdk",
            })
          }
        >
          axiom-sdk
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

function ti(container: HTMLElement, id: string): HTMLElement | null {
  return container.querySelector(`[data-testid="${id}"]`);
}

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
  container.style.width = "1300px";
  document.body.appendChild(container);
  const root = createRoot(container);
  await act(async () => {
    root.render(
      <Workspace
        workspaceId="ws-axiom"
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
  return { root, container };
}

function constellation(container: HTMLElement): HTMLElement | null {
  return container.querySelector('[data-omnix-brain="1"]');
}

describe("slice15.1 atomic drill integration", () => {
  it("galaxy → cluster: single render asserts six synchronized surfaces", async () => {
    const { root, container } = await renderWorkspace();
    const galaxy = container.querySelector<HTMLButtonElement>(
      '[data-omnix-drill="galaxy-axiom"]'
    );
    expect(galaxy).toBeTruthy();

    await act(async () => {
      galaxy!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    await act(async () => {
      const bc = ti(container, "breadcrumb");
      expect(bc?.textContent).toContain("AXIOM-V2");
      expect(ti(container, "xray-name")?.textContent?.trim()).toBe("AXIOM-V2");
      expect(ti(container, "xray-badge")?.textContent?.trim()).toBe("MODULE");
      expect(ti(container, "stats-files")?.textContent?.trim()).toBe(
        String(fixture.statsAv2.files)
      );
      expect(
        [...container.querySelectorAll("*")].some(
          (el) => el.textContent === "Whole graph intelligence"
        )
      ).toBe(false);
      const cons = constellation(container);
      expect(cons).toBeTruthy();
      expect(cons!.querySelectorAll("[data-omnix-node]").length).toBe(
        fixture.av2ScopedNodeCount
      );
    });

    await act(async () => {
      root.unmount();
    });
  });

  it("cluster → file scope: breadcrumb three segments + synchronized surfaces", async () => {
    const { root, container } = await renderWorkspace();
    await act(async () => {
      container
        .querySelector('[data-omnix-drill="galaxy-axiom"]')!
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await act(async () => {
      container
        .querySelector('[data-testid="go-crypto"]')!
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    await act(async () => {
      const bc = ti(container, "breadcrumb");
      expect(bc?.textContent).toContain("OMNIX");
      expect(bc?.textContent).toContain("AXIOM-V2");
      expect(bc?.textContent).toContain("crypto");
      expect(ti(container, "xray-name")?.textContent?.trim()).toBe("crypto");
      expect(ti(container, "xray-badge")?.textContent?.trim()).toBe("MODULE");
      expect(ti(container, "stats-files")?.textContent?.trim()).toBe(
        String(fixture.statsCrypto.files)
      );
      expect(
        [...container.querySelectorAll("*")].some(
          (el) => el.textContent === "Whole graph intelligence"
        )
      ).toBe(false);
      const cons = constellation(container);
      expect(cons!.querySelectorAll("[data-omnix-node]").length).toBe(
        fixture.cryptoScopedNodeCount
      );
    });

    await act(async () => {
      root.unmount();
    });
  });

  it("leaf selection: FUNCTION badge + Brain tab body non-empty", async () => {
    const { root, container } = await renderWorkspace();
    await act(async () => {
      container
        .querySelector('[data-testid="go-crypto"]')!
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    await act(async () => {
      container
        .querySelector('[data-testid="pick-fn"]')!
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    await act(async () => {
      expect(ti(container, "xray-badge")?.textContent?.toUpperCase()).toContain(
        "FUNCTION"
      );
      const innerBrain = [...container.querySelectorAll(".xray-itabs [role='tab']")].find(
        (b) => b.textContent?.trim().toUpperCase() === "BRAIN"
      );
      expect(innerBrain).toBeTruthy();
      innerBrain!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
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

  it("breadcrumb walk-up: repo-level six surfaces in one act", async () => {
    const { root, container } = await renderWorkspace();
    await act(async () => {
      container
        .querySelector('[data-testid="pick-fn"]')!
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });
    const omnix = [...container.querySelectorAll("button")].find(
      (b) => b.textContent?.trim() === "OMNIX"
    );
    expect(omnix).toBeTruthy();

    await act(async () => {
      omnix!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    await act(async () => {
      const bc = ti(container, "breadcrumb");
      expect(bc?.textContent).not.toContain("AXIOM-V2");
      expect(ti(container, "xray-badge")?.textContent?.trim()).toBe("REPO");
      expect(ti(container, "xray-name")?.textContent?.trim()).toBe("Workspace");
      expect(ti(container, "stats-files")?.textContent?.trim()).toBe(
        String(fixture.statsRepo.files)
      );
      const cons = constellation(container);
      expect(cons!.querySelectorAll("[data-omnix-node]").length).toBe(
        fixture.repoGalaxyDirCount
      );
    });

    await act(async () => {
      root.unmount();
    });
  });

  it("rapid drill stress: final scope matches last intentional click", async () => {
    const { root, container } = await renderWorkspace();

    await act(async () => {
      container
        .querySelector('[data-omnix-drill="galaxy-axiom"]')!
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
      const omnix = [...container.querySelectorAll("button")].find(
        (b) => b.textContent?.trim() === "OMNIX"
      );
      omnix!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
      container
        .querySelector('[data-omnix-drill="galaxy-axiom"]')!
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
      container
        .querySelector('[data-omnix-drill="galaxy-pkg"]')!
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    await act(async () => {
      expect(ti(container, "stats-files")?.textContent?.trim()).toBe(
        String(fixture.statsPkg.files)
      );
      expect(ti(container, "xray-name")?.textContent?.trim()).toBe("axiom-sdk");
      const cons = constellation(container);
      expect(cons!.querySelectorAll("[data-omnix-node]").length).toBe(
        fixture.pkgScopedNodeCount
      );
    });

    await act(async () => {
      root.unmount();
    });
  });
});
