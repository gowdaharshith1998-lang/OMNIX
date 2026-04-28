import { describe, expect, it, vi } from "vitest";
import { StudioGraph } from "../StudioGraph";

vi.mock("../viewerEngine", () => ({
  installOmnixViewerEngine: (studio: {
    _loadGraphFromData?: ReturnType<typeof vi.fn>;
    _destroy?: ReturnType<typeof vi.fn>;
    _flashNodeRim?: ReturnType<typeof vi.fn>;
    _fadeAndRemoveNode?: ReturnType<typeof vi.fn>;
  }) => {
    studio._loadGraphFromData = vi.fn();
    studio._destroy = vi.fn();
    studio._flashNodeRim = vi.fn();
    studio._fadeAndRemoveNode = vi.fn();
  },
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

function fadeSpy(g: StudioGraph) {
  return (g as unknown as { _studio: { _fadeAndRemoveNode: ReturnType<typeof vi.fn> } })
    ._studio._fadeAndRemoveNode;
}

function planetReady(g: StudioGraph) {
  (
    g as unknown as {
      _studio: { setViewContext?: (c: "planet-ready" | "non-planet") => void };
    }
  )._studio.setViewContext?.("planet-ready");
}

describe("node_removed after bootstrap", () => {
  it("resolves ws_id to synth id, calls _fadeAndRemoveNode, and removes map entry", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const fade = fadeSpy(g);

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
    planetReady(g);

    const map = (g as unknown as { _wsIdToSynthId: Map<string, string> })._wsIdToSynthId;
    expect(map.get("raw123")).toBe("x.py::foo");

    g.ingestDelta({ type: "node_removed", node_id: "raw123" });

    expect(fade).toHaveBeenCalledTimes(1);
    expect(fade).toHaveBeenCalledWith("x.py::foo", {
      durationMs: 400,
    });
    expect(map.has("raw123")).toBe(false);
  });
});
