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

describe("duplicate node_added", () => {
  it("second node_added for same ws id is no-op", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const born = bornSpy(g);

    g.ingestDelta({ type: "bootstrap_start" });
    g.ingestDelta({
      type: "node_added",
      node: {
        id: "raw123",
        name: "foo",
        type: "function",
        file_path: "x.py",
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
        id: "raw123",
        name: "foo",
        type: "function",
        file_path: "x.py",
        line_start: 1,
        line_end: 2,
      },
    });

    expect(born).not.toHaveBeenCalled();
  });
});
