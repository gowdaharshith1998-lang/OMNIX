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

function loadSpy(g: StudioGraph) {
  return (g as unknown as { _studio: { _loadGraphFromData: ReturnType<typeof vi.fn> } })
    ._studio._loadGraphFromData;
}

describe("edge_added during bootstrap buffer window", () => {
  it("buffers edge_added into _bootstrapBuffer.edges (snapshot shape), does not call _bornEdge until after complete", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const bornEdge = edgeSpy(g);
    const load = loadSpy(g);

    g.ingestDelta({ type: "bootstrap_start" });
    /* Buffered snapshot uses wsEdgeToLinkShape (source_id/target_id). */
    g.ingestDelta({
      type: "edge_added",
      edge: {
        id: 42,
        source_id: "na",
        target_id: "nb",
        relationship: "CALLS",
      },
    });

    expect(bornEdge).not.toHaveBeenCalled();

    g.ingestDelta({
      type: "bootstrap_complete",
      duration_ms: 0,
      total_nodes: 0,
      total_edges: 1,
    });

    expect(load).toHaveBeenCalledTimes(1);
    const arg = load.mock.calls[0]![0] as { links: unknown[] };
    expect(arg.links.length).toBe(1);
    const link0 = arg.links[0] as Record<string, unknown>;
    expect(link0.source).toBe("na");
    expect(link0.target).toBe("nb");
  });
});
