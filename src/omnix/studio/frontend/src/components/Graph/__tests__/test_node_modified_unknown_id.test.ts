import { describe, expect, it, vi } from "vitest";
import { StudioGraph } from "../StudioGraph";

vi.mock("../viewerEngine", () => ({
  installOmnixViewerEngine: (studio: {
    _loadGraphFromData?: ReturnType<typeof vi.fn>;
    _destroy?: ReturnType<typeof vi.fn>;
    _flashNodeRim?: ReturnType<typeof vi.fn>;
  }) => {
    studio._loadGraphFromData = vi.fn();
    studio._destroy = vi.fn();
    studio._flashNodeRim = vi.fn();
  },
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

function flashSpy(g: StudioGraph) {
  return (g as unknown as { _studio: { _flashNodeRim: ReturnType<typeof vi.fn> } })
    ._studio._flashNodeRim;
}

describe("node_modified unknown ws_id", () => {
  it("does not call _flashNodeRim or throw", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const flash = flashSpy(g);

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

    g.ingestDelta({ type: "node_modified", node_id: "raw999" });

    expect(flash).not.toHaveBeenCalled();
  });
});
