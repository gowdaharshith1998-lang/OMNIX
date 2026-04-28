import { describe, expect, it, vi } from "vitest";
import { StudioGraph } from "../StudioGraph";

vi.mock("../viewerEngine", () => ({
  installOmnixViewerEngine: (studio: {
    _loadGraphFromData?: ReturnType<typeof vi.fn>;
    _destroy?: ReturnType<typeof vi.fn>;
    _bornNode?: ReturnType<typeof vi.fn>;
    _bornEdge?: ReturnType<typeof vi.fn>;
  }) => {
    studio._loadGraphFromData = vi.fn();
    studio._destroy = vi.fn();
    studio._bornNode = vi.fn(() => true);
    studio._bornEdge = vi.fn(() => true);
  },
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

function edgeSpy(g: StudioGraph) {
  return (g as unknown as { _studio: { _bornEdge: ReturnType<typeof vi.fn> } })._studio
    ._bornEdge;
}

describe("edge_added after bootstrap", () => {
  it("calls _bornEdge with resolved synth ids when both endpoints exist", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const bornEdge = edgeSpy(g);

    g.ingestDelta({ type: "bootstrap_start" });
    g.ingestDelta({
      type: "node_added",
      node: {
        id: "rawA",
        name: "alpha",
        type: "function",
        file_path: "shared.py",
        line_start: 1,
        line_end: 2,
      },
    });
    g.ingestDelta({
      type: "node_added",
      node: {
        id: "rawB",
        name: "beta",
        type: "function",
        file_path: "shared.py",
        line_start: 3,
        line_end: 4,
      },
    });
    g.ingestDelta({
      type: "bootstrap_complete",
      duration_ms: 0,
      total_nodes: 2,
      total_edges: 0,
    });

    g.ingestDelta({
      type: "edge_added",
      edge: {
        id: 1,
        from_id: "rawA",
        to_id: "rawB",
        relationship: "CALLS",
      },
    });

    expect(bornEdge).toHaveBeenCalledTimes(1);
    expect(bornEdge.mock.calls[0]![0]).toBe("shared.py::alpha");
    expect(bornEdge.mock.calls[0]![1]).toBe("shared.py::beta");
  });
});
