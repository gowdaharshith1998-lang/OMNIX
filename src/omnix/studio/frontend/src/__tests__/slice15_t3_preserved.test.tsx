import { describe, expect, it, vi } from "vitest";
import { StudioGraph } from "@/components/Graph/StudioGraph";

vi.mock("@/components/Graph/viewerEngine", () => ({
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

function planetReady(g: StudioGraph) {
  (
    g as unknown as {
      _studio: { setViewContext?: (c: "planet-ready" | "non-planet") => void };
    }
  )._studio.setViewContext?.("planet-ready");
}

describe("slice15 T3 live emission preserved", () => {
  it("node_added after bootstrap invokes _bornNode on the same synchronous turn", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const born = bornSpy(g);

    g.ingestDelta({ type: "bootstrap_start" });
    g.ingestDelta({
      type: "node_added",
      node: {
        id: "live-a",
        name: "alpha",
        type: "function",
        file_path: "slice15_a.py",
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
    planetReady(g);

    let callsImmediatelyAfter = born.mock.calls.length;
    expect(callsImmediatelyAfter).toBe(0);

    g.ingestDelta({
      type: "node_added",
      node: {
        id: "live-b",
        name: "beta",
        type: "function",
        file_path: "slice15_b.py",
        line_start: 3,
        line_end: 4,
      },
    });

    callsImmediatelyAfter = born.mock.calls.length;
    expect(callsImmediatelyAfter).toBe(1);
    expect(born.mock.calls[0]![0]).toBe("live-b");

    g.destroy();
  });
});
