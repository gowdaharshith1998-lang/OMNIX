import { describe, expect, it, vi } from "vitest";
import { StudioGraph } from "../StudioGraph";

vi.mock("../viewerEngine", () => ({
  installOmnixViewerEngine: (studio: {
    _loadGraphFromData?: ReturnType<typeof vi.fn>;
    _destroy?: ReturnType<typeof vi.fn>;
    _bornEdge?: ReturnType<typeof vi.fn>;
  }) => {
    studio._loadGraphFromData = vi.fn();
    studio._destroy = vi.fn();
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

describe("edge_added missing workspace endpoint", () => {
  it("does not call _bornEdge when one ws id is unknown to the map", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const bornEdge = edgeSpy(g);

    g.ingestDelta({ type: "bootstrap_start" });
    g.ingestDelta({
      type: "node_added",
      node: {
        id: "rawOnly",
        name: "solo",
        type: "function",
        file_path: "one.py",
        line_start: 1,
        line_end: 1,
      },
    });
    g.ingestDelta({
      type: "bootstrap_complete",
      duration_ms: 0,
      total_nodes: 1,
      total_edges: 0,
    });

    g.ingestDelta({
      type: "edge_added",
      edge: {
        id: 9,
        from_id: "rawOnly",
        to_id: "rawNeverSeen",
        relationship: "CALLS",
      },
    });

    expect(bornEdge).not.toHaveBeenCalled();
  });
});
