import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT =
  true;

import { resetStudioScopeForTests } from "@/store/studioScopeStore";
import type { ScopeNavigationSpec } from "@/components/Graph/StudioGraph";

const callLog: string[] = [];

vi.mock("@/components/Graph/viewerEngine", () => ({
  installOmnixViewerEngine: (studio: {
    _container: HTMLElement;
    _pauseRenderLoop?: () => void;
    _resumeRenderLoop?: () => void;
    _destroy?: () => void;
    _loadGraphFromData?: (data: unknown) => void;
  }) => {
    const canvas = document.createElement("canvas");
    studio._container.appendChild(canvas);
    studio._pauseRenderLoop = () => {
      callLog.push("pauseRenderLoop");
    };
    studio._resumeRenderLoop = () => {
      callLog.push("resumeRenderLoop");
    };
    studio._destroy = () => {
      callLog.push("dispose");
      if (canvas.parentNode) {
        canvas.parentNode.removeChild(canvas);
      }
    };
    studio._loadGraphFromData = vi.fn();
  },
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

import { GraphCanvas } from "@/components/Graph/GraphCanvas";
import { StudioGraph } from "@/components/Graph/StudioGraph";

afterEach(() => {
  resetStudioScopeForTests();
  callLog.length = 0;
});

describe("slice 15.2 cleanup order", () => {
  it("unmount runs pauseRenderLoop then dispose (stops ticker before GPU teardown)", async () => {
    const el = document.createElement("div");
    document.body.appendChild(el);
    const root = createRoot(el);

    await act(async () => {
      root.render(
        <GraphCanvas
          drillDownNodeId={null}
          navigationSpec={{ kind: "repo" } satisfies ScopeNavigationSpec}
          onFunctionNodeClick={() => {}}
          onFileOrDirClick={() => {}}
          onDeselect={() => {}}
          onNavigationStateChange={() => {}}
        />
      );
    });

    await act(async () => {
      root.unmount();
    });

    const pauseIdx = callLog.indexOf("pauseRenderLoop");
    const disposeIdx = callLog.indexOf("dispose");
    expect(pauseIdx).toBeGreaterThanOrEqual(0);
    expect(disposeIdx).toBeGreaterThan(pauseIdx);

    document.body.removeChild(el);
  });

  it("disposeAll is idempotent — second dispose does not throw", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    expect(() => {
      g.disposeAll();
      g.disposeAll();
    }).not.toThrow();
  });

  it("cleanup with null engine handles — disposeAll is a no-op without throwing", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const studio = (
      g as unknown as {
        _studio: { _destroy?: () => void; _pauseRenderLoop?: () => void };
      }
    )._studio;
    studio._destroy = undefined;
    studio._pauseRenderLoop = undefined;

    expect(() => g.disposeAll()).not.toThrow();
  });
});
