import { describe, expect, it, vi } from "vitest";
import { StudioGraph } from "../StudioGraph";

vi.mock("../viewerEngine", () => ({
  installOmnixViewerEngine: (studio: {
    _loadGraphFromData?: ReturnType<typeof vi.fn>;
    _destroy?: ReturnType<typeof vi.fn>;
    _bornEdge?: ReturnType<typeof vi.fn>;
    _fadeAndRemoveNode?: ReturnType<typeof vi.fn>;
  }) => {
    studio._loadGraphFromData = vi.fn();
    studio._destroy = vi.fn();
    studio._bornEdge = vi.fn(() => true);
    studio._fadeAndRemoveNode = vi.fn();
  },
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

describe("edge_added then node_removed of endpoint", () => {
  it("does not throw when removing an endpoint after a live edge dispatch", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});

    g.ingestDelta({ type: "bootstrap_start" });
    g.ingestDelta({
      type: "node_added",
      node: {
        id: "rawE1",
        name: "e1",
        type: "function",
        file_path: "mix.py",
        line_start: 1,
        line_end: 1,
      },
    });
    g.ingestDelta({
      type: "node_added",
      node: {
        id: "rawE2",
        name: "e2",
        type: "function",
        file_path: "mix.py",
        line_start: 2,
        line_end: 2,
      },
    });
    g.ingestDelta({
      type: "bootstrap_complete",
      duration_ms: 0,
      total_nodes: 2,
      total_edges: 0,
    });

    expect(() => {
      g.ingestDelta({
        type: "edge_added",
        edge: {
          id: 77,
          from_id: "rawE1",
          to_id: "rawE2",
          relationship: "CALLS",
        },
      });
      g.ingestDelta({ type: "node_removed", node_id: "rawE2" });
      g.ingestDelta({
        type: "edge_added",
        edge: {
          id: 78,
          from_id: "rawE1",
          to_id: "rawE2",
          relationship: "CALLS",
        },
      });
    }).not.toThrow();
  });
});
