import { describe, expect, it, vi } from "vitest";
import { StudioGraph } from "../StudioGraph";

vi.mock("../viewerEngine", () => ({
  installOmnixViewerEngine: (studio: {
    _loadGraphFromData?: ReturnType<typeof vi.fn>;
    _destroy?: ReturnType<typeof vi.fn>;
    _bornNode?: ReturnType<typeof vi.fn>;
  }) => {
    studio._loadGraphFromData = vi.fn();
    studio._destroy = vi.fn();
    studio._bornNode = vi.fn(() => true);
  },
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

function bornSpy(g: StudioGraph) {
  return (g as unknown as { _studio: { _bornNode: ReturnType<typeof vi.fn> } })._studio
    ._bornNode;
}

describe("node_added after bootstrap", () => {
  it("calls _bornNode with ws id, viewer-shaped payload, and 400ms opts", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const born = bornSpy(g);

    g.ingestDelta({ type: "bootstrap_start" });
    g.ingestDelta({
      type: "node_added",
      node: {
        id: "rawA",
        name: "alpha",
        type: "function",
        file_path: "a.py",
        line_start: 1,
        line_end: 2,
      },
    });
    g.ingestDelta({
      type: "bootstrap_complete",
      duration_ms: 0,
      total_nodes: 1,
      total_edges: 0,
    });

    g.ingestDelta({
      type: "node_added",
      node: {
        id: "rawB",
        name: "beta",
        type: "function",
        file_path: "b.py",
        line_start: 3,
        line_end: 4,
      },
    });

    expect(born).toHaveBeenCalledTimes(1);
    const argWs = born.mock.calls[0]![0];
    const argShape = born.mock.calls[0]![1] as Record<string, unknown>;
    const argOpts = born.mock.calls[0]![2];
    expect(argWs).toBe("rawB");
    expect(argShape.id).toBe("b.py::beta");
    expect(argOpts).toEqual({ durationMs: 400 });

    const map = (g as unknown as { _wsIdToSynthId: Map<string, string> })._wsIdToSynthId;
    expect(map.get("rawB")).toBe("b.py::beta");
  });
});
