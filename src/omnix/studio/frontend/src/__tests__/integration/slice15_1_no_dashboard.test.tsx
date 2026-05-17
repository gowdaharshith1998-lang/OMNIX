import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeAll, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

import { CANONICAL_SCOPES, scopeRecordsToMaps } from "@/store/scopeRegistry";
import { resetStudioScopeForTests } from "@/store/studioScopeStore";
import type { ScopeNavigationSpec } from "@/components/Graph/StudioGraph";
import type { GraphEdge, GraphNode } from "@/types/drilldown";
import { loadAxiomFixture } from "./axiomFixture";

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
  getFile: vi.fn(() => Promise.resolve({ path: "", content: "", last_modified: 0, language: "txt" })),
  putFile: vi.fn(),
  searchWorkspace: vi.fn(() => Promise.resolve({ hits: [] })),
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

vi.mock("@/components/Graph/GraphCanvas", () => ({
  GraphCanvas: React.forwardRef(function MockGraphCanvas(
    _props: { navigationSpec: ScopeNavigationSpec },
    ref: React.Ref<{ simulateRenderError?: () => void }>
  ) {
    React.useImperativeHandle(ref, () => ({
      ingestMessage: vi.fn(),
      canGoBack: () => false,
      goBack: vi.fn(),
      applyScopeNavigation: vi.fn(),
      simulateRenderError: vi.fn(),
    }));
    return <div data-testid="mock-graph" />;
  }),
}));

let fixture!: ReturnType<typeof loadAxiomFixture>;

beforeAll(() => {
  fixture = loadAxiomFixture();
});

import { Workspace } from "@/components/Workspace";
import { XRayTab } from "@/components/XRayTab";

afterEach(() => {
  document.body.textContent = "";
  resetStudioScopeForTests();
});

describe("slice15.1 no legacy X-Ray dashboard", () => {
  it("does not surface HEALTH bar labels in X-Ray", async () => {
    const { byId } = scopeRecordsToMaps(CANONICAL_SCOPES);
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <XRayTab
          workspaceId="w"
          scopeAtomId="repo"
          graphNodes={new Map()}
          graphEdges={[]}
          stats={{
            files: 0,
            functions: 0,
            classes: 0,
            edges: 0,
            dark_matter: 0,
            entangled: 0,
          }}
          scopeById={byId}
          projectPath="/proj"
          bugsScanFindings={[]}
          bugsScanSummary={null}
          onSuggestedAction={() => undefined}
        />
      );
    });
    expect(container.textContent?.includes("Complexity")).toBe(false);
    expect(container.textContent?.includes("Connectivity")).toBe(false);
    expect(container.textContent?.includes("Entanglement risk")).toBe(false);
    await act(async () => root.unmount());
  });

  it("does not show AI Agent unavailable copy in X-Ray", async () => {
    const { byId } = scopeRecordsToMaps(CANONICAL_SCOPES);
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <XRayTab
          workspaceId="w"
          scopeAtomId="repo"
          graphNodes={new Map()}
          graphEdges={[]}
          stats={{
            files: 0,
            functions: 0,
            classes: 0,
            edges: 0,
            dark_matter: 0,
            entangled: 0,
          }}
          scopeById={byId}
          projectPath="/proj"
          bugsScanFindings={[]}
          bugsScanSummary={null}
          onSuggestedAction={() => undefined}
        />
      );
    });
    expect(container.textContent?.match(/AI Agent unavailable/i)).toBeNull();
    await act(async () => root.unmount());
  });

  it("does not embed DIAGNOSTICS god-file / complexity cards in default Code tab", async () => {
    const { byId } = scopeRecordsToMaps(CANONICAL_SCOPES);
    const bigNodes = new Map<string, GraphNode>();
    for (let i = 0; i < 120; i++) {
      bigNodes.set(`n${i}`, {
        id: `n${i}`,
        name: `fn${i}`,
        type: "function",
        file_path: "pkg/heavy.py",
        line_start: i,
        line_end: i,
      });
    }
    const edges: GraphEdge[] = [];
    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);
    await act(async () => {
      root.render(
        <XRayTab
          workspaceId="w"
          scopeAtomId="repo"
          graphNodes={bigNodes}
          graphEdges={edges}
          stats={{
            files: 1,
            functions: 120,
            classes: 0,
            edges: 0,
            dark_matter: 0,
            entangled: 0,
          }}
          scopeById={byId}
          projectPath="/proj"
          bugsScanFindings={[]}
          bugsScanSummary={null}
          onSuggestedAction={() => undefined}
        />
      );
    });
    expect(container.textContent?.match(/God file:/i)).toBeNull();
    expect(container.textContent?.match(/High complexity:/i)).toBeNull();
    await act(async () => root.unmount());
  });

  it("exposes exactly one stats-files test id under the constellation stats card", async () => {
    const container = document.createElement("div");
    container.style.width = "1300px";
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
    const doc = container.ownerDocument;
    const statsEls = doc.querySelectorAll('[data-testid="stats-files"]');
    expect(statsEls.length).toBe(1);
    expect(statsEls[0]?.closest('[data-omnix-stats-card="1"]')).not.toBeNull();
    await act(async () => root.unmount());
  });
});
