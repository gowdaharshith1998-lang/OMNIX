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
    let n = 0;
    studio._bornEdge = vi.fn(() => {
      n += 1;
      return n === 1;
    });
  },
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

function edgeSpy(g: StudioGraph) {
  return (g as unknown as { _studio: { _bornEdge: ReturnType<typeof vi.fn> } })._studio
    ._bornEdge;
}

function planetReady(g: StudioGraph) {
  (
    g as unknown as {
      _studio: { setViewContext?: (c: "planet-ready" | "non-planet") => void };
    }
  )._studio.setViewContext?.("planet-ready");
}

describe("edge_added duplicate unordered pair", () => {
  it("invokes _bornEdge twice; second live dispatch still attempts viewer (viewer returns false)", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const bornEdge = edgeSpy(g);

    g.ingestDelta({ type: "bootstrap_start" });
    g.ingestDelta({
      type: "node_added",
      node: {
        id: "rawA",
        name: "a",
        type: "function",
        file_path: "dup.py",
        line_start: 1,
        line_end: 1,
      },
    });
    g.ingestDelta({
      type: "node_added",
      node: {
        id: "rawB",
        name: "b",
        type: "function",
        file_path: "dup.py",
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
    planetReady(g);

    const edgePayload = {
      type: "edge_added" as const,
      edge: {
        id: 1,
        from_id: "rawA",
        to_id: "rawB",
        relationship: "CALLS",
      },
    };

    g.ingestDelta(edgePayload);
    g.ingestDelta(edgePayload);

    expect(bornEdge).toHaveBeenCalledTimes(2);
    expect(bornEdge.mock.calls[0]![0]).toBe("dup.py::a");
    expect(bornEdge.mock.calls[0]![1]).toBe("dup.py::b");
    expect(bornEdge.mock.calls[1]![0]).toBe("dup.py::a");
    expect(bornEdge.mock.calls[1]![1]).toBe("dup.py::b");
  });
});
