import { describe, expect, it, vi } from "vitest";
import { StudioGraph } from "../StudioGraph";

vi.mock("../viewerEngine", () => ({
  installOmnixViewerEngine: (studio: {
    _loadGraphFromData?: ReturnType<typeof vi.fn>;
    _destroy?: ReturnType<typeof vi.fn>;
  }) => {
    studio._loadGraphFromData = vi.fn();
    studio._destroy = vi.fn();
  },
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

function loadSpy(g: StudioGraph) {
  return (g as unknown as { _studio: { _loadGraphFromData: ReturnType<typeof vi.fn> } })
    ._studio._loadGraphFromData;
}

describe("bootstrap buffer collects messages", () => {
  it("buffers node_added and edge_added then calls _loadGraphFromData once with correct counts", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const spy = loadSpy(g);

    g.ingestDelta({ type: "bootstrap_start" });
    for (let i = 0; i < 100; i++) {
      g.ingestDelta({
        type: "node_added",
        node: {
          id: `n${i}`,
          name: `name${i}`,
          type: "function",
          file_path: `f/${i}.py`,
          line_start: i,
          line_end: i,
        },
      });
    }
    for (let i = 0; i < 50; i++) {
      g.ingestDelta({
        type: "edge_added",
        edge: {
          id: i,
          source_id: `n${i}`,
          target_id: `n${i + 1}`,
          relationship: "CALLS",
          metadata: {},
        },
      });
    }
    g.ingestDelta({
      type: "bootstrap_complete",
      duration_ms: 1,
      total_nodes: 100,
      total_edges: 50,
    });

    expect(spy).toHaveBeenCalledTimes(1);
    const arg = spy.mock.calls[0]![0] as {
      nodes: unknown[];
      links: unknown[];
    };
    expect(arg.nodes.length).toBe(100);
    expect(arg.links.length).toBe(50);
  });
});
