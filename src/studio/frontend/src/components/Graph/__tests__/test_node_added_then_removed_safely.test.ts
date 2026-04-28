import { describe, expect, it, vi } from "vitest";
import { StudioGraph } from "../StudioGraph";

vi.mock("../viewerEngine", () => ({
  installOmnixViewerEngine: (studio: {
    _loadGraphFromData?: ReturnType<typeof vi.fn>;
    _destroy?: ReturnType<typeof vi.fn>;
    _bornNode?: ReturnType<typeof vi.fn>;
    _fadeAndRemoveNode?: ReturnType<typeof vi.fn>;
  }) => {
    studio._loadGraphFromData = vi.fn();
    studio._destroy = vi.fn();
    studio._bornNode = vi.fn(() => true);
    studio._fadeAndRemoveNode = vi.fn();
  },
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

function bornSpy(g: StudioGraph) {
  return (g as unknown as { _studio: { _bornNode: ReturnType<typeof vi.fn> } })._studio
    ._bornNode;
}

function fadeSpy(g: StudioGraph) {
  return (g as unknown as { _studio: { _fadeAndRemoveNode: ReturnType<typeof vi.fn> } })
    ._studio._fadeAndRemoveNode;
}

describe("node_added then node_removed quickly", () => {
  it("registers map, removes cleanly within 100ms window", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const born = bornSpy(g);
    const fade = fadeSpy(g);

    g.ingestDelta({ type: "bootstrap_start" });
    g.ingestDelta({
      type: "node_added",
      node: {
        id: "rawA",
        name: "a",
        type: "function",
        file_path: "a.py",
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
      type: "node_added",
      node: {
        id: "rawB",
        name: "b",
        type: "class",
        file_path: "b.py",
        line_start: 2,
        line_end: 2,
      },
    });

    const map = (g as unknown as { _wsIdToSynthId: Map<string, string> })._wsIdToSynthId;
    expect(map.get("rawB")).toBe("b.py::b");

    g.ingestDelta({ type: "node_removed", node_id: "rawB" });

    expect(born).toHaveBeenCalledTimes(1);
    expect(fade).toHaveBeenCalledTimes(1);
    expect(fade).toHaveBeenCalledWith("b.py::b", { durationMs: 400 });
    expect(map.has("rawB")).toBe(false);
  });
});
