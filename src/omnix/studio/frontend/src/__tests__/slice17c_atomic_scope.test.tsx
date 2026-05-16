import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

import type { GraphEdge, GraphNode } from "@/types/drilldown";
import { resetStudioScopeForTests } from "@/store/studioScopeStore";
import type { ScopeNavigationSpec } from "@/components/Graph/StudioGraph";
import { loadAxiomFixture } from "./integration/axiomFixture";

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
      onScopeVisualEmpty?: (d: { scopePath: string } | null) => void;
      onFunctionNodeClick?: (id: string) => void;
      onT1GraphNodes?: (nodes: GraphNode[]) => void;
      onT1GraphEdges?: (edges: GraphEdge[]) => void;
    },
    ref: React.Ref<{
      applyScopeNavigation: (s: ScopeNavigationSpec) => void;
      ingestMessage: (m: unknown) => void;
      canGoBack: () => boolean;
      goBack: () => void;
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
      canGoBack: () => scene !== "repo",
      goBack: vi.fn(() => {
        props.onViewerScope?.({ kind: "repo" });
      }),
      applyScopeNavigation: vi.fn(),
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

describe("slice17c atomic scope coordination", () => {
  it("single act batch: galaxy click updates X-Ray header, stats, diagnostics scope key, constellation echo", async () => {
    const { root, container } = await renderWorkspace();
    await act(async () => {
      container
        .querySelector<HTMLButtonElement>('[data-omnix-drill="galaxy-axiom"]')!
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    await act(async () => {
      expect(ti(container, "xray-name")?.textContent?.trim()).toBe("AXIOM-V2");
      expect(ti(container, "stats-files")?.textContent?.trim()).toBe(
        String(fixture.statsAv2.files)
      );
      const cons = container.querySelector('[data-omnix-brain="1"]');
      expect(cons?.getAttribute("data-studio-viewer-scope-path")).toBe(
        "apps/backend/src/omnix/axiom"
      );
      const diag = [...container.querySelectorAll(".xray-itabs [role='tab']")].find(
        (b) => b.textContent?.trim() === "Diagnostics"
      );
      diag?.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    await act(async () => {
      const key = ti(container, "xray-diagnostics-scope-key");
      expect(key?.textContent?.trim()).not.toBe("repo");
    });

    await act(async () => {
      root.unmount();
    });
  });

  it("multi-level drill repo → axiom → crypto → function leaf", async () => {
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
      container
        .querySelector('[data-testid="pick-fn"]')!
        .dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    await act(async () => {
      expect(ti(container, "xray-badge")?.textContent?.toUpperCase()).toContain(
        "FUNCTION"
      );
      expect(ti(container, "xray-path")?.textContent).toContain("hybrid_signer");
      const cons = container.querySelector('[data-omnix-brain="1"]');
      expect(cons?.getAttribute("data-studio-viewer-scope-path")).toBe(
        "apps/backend/src/omnix/axiom/services/crypto"
      );
    });

    await act(async () => {
      root.unmount();
    });
  });

  it("breadcrumb ancestor returns stats toward repo scope", async () => {
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

    const bc = ti(container, "breadcrumb");
    const ancestor = [...bc!.querySelectorAll("button")].find(
      (b) => b.textContent?.trim() === "AXIOM-V2"
    );
    expect(ancestor).toBeTruthy();

    await act(async () => {
      ancestor!.dispatchEvent(new MouseEvent("click", { bubbles: true }));
    });

    await act(async () => {
      expect(ti(container, "stats-files")?.textContent?.trim()).toBe(
        String(fixture.statsAv2.files)
      );
    });

    await act(async () => {
      root.unmount();
    });
  });

  it("function leaf: FUNCTION badge + Code tab shows source", async () => {
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
});
