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

describe("single rebuild per bootstrap", () => {
  it("calls _loadGraphFromData once after 1000 node_added messages", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const spy = loadSpy(g);

    g.ingestDelta({ type: "bootstrap_start" });
    for (let i = 0; i < 1000; i++) {
      g.ingestDelta({
        type: "node_added",
        node: {
          id: `id${i}`,
          name: `n${i}`,
          type: "function",
          file_path: "pkg/mod.py",
          line_start: 1,
          line_end: 2,
        },
      });
    }
    g.ingestDelta({
      type: "bootstrap_complete",
      duration_ms: 10,
      total_nodes: 1000,
      total_edges: 0,
    });

    expect(spy).toHaveBeenCalledTimes(1);
    const arg = spy.mock.calls[0]![0] as { nodes: unknown[] };
    expect(arg.nodes.length).toBe(1000);
  });
});
