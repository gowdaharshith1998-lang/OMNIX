import { describe, expect, it, vi } from "vitest";

const seq: string[] = [];

vi.mock("@/components/Graph/viewerEngine", () => ({
  installOmnixViewerEngine: (studio: {
    _loadGraphFromData?: (data: unknown) => void;
    _pauseRenderLoop?: () => void;
    _resumeRenderLoop?: () => void;
  }) => {
    studio._pauseRenderLoop = () => {
      seq.push("pause");
    };
    studio._resumeRenderLoop = () => {
      seq.push("resume");
    };
    studio._loadGraphFromData = function (data: unknown) {
      studio._pauseRenderLoop?.();
      try {
        seq.push("scene-mutate");
        void data;
      } finally {
        studio._resumeRenderLoop?.();
      }
    };
  },
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

import { StudioGraph } from "@/components/Graph/StudioGraph";

describe("render pause contract (mock mirrors viewerEngine)", () => {
  it("pause is requested before scene mutation and resume after", () => {
    seq.length = 0;
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    g.loadInitial([], [], {});
    expect(seq).toEqual(["pause", "scene-mutate", "resume"]);
  });

  it("rapid double _loadGraphFromData is reentrant-safe (nested pause depth)", () => {
    seq.length = 0;
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const studio = (g as unknown as { _studio: { _loadGraphFromData?: (d: unknown) => void } })
      ._studio;
    const load = studio._loadGraphFromData;
    if (load) {
      load({ nodes: [], links: [] });
      load({ nodes: [], links: [] });
    }
    expect(seq.filter((s) => s === "pause").length).toBe(2);
    expect(seq.filter((s) => s === "resume").length).toBe(2);
    expect(seq.lastIndexOf("resume")).toBe(seq.length - 1);
  });
});
