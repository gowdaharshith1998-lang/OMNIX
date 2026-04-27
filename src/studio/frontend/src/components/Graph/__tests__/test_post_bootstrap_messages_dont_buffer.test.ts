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

describe("post-bootstrap node_added", () => {
  it("does not trigger a second _loadGraphFromData", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const spy = loadSpy(g);

    g.ingestDelta({ type: "bootstrap_start" });
    g.ingestDelta({
      type: "node_added",
      node: {
        id: "a",
        name: "a",
        type: "function",
        file_path: "x.py",
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
    expect(spy).toHaveBeenCalledTimes(1);

    g.ingestDelta({
      type: "node_added",
      node: {
        id: "late",
        name: "late",
        type: "class",
        file_path: "y.py",
        line_start: 2,
        line_end: 2,
      },
    });
    expect(spy).toHaveBeenCalledTimes(1);
  });
});
