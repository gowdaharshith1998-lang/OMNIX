import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
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

function flashSpy(g: StudioGraph) {
  return (g as unknown as { _studio: { _flashNodeRim: ReturnType<typeof vi.fn> } })
    ._studio._flashNodeRim;
}

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

describe("node_removed then node_modified same ws id", () => {
  let debugSpy: ReturnType<typeof vi.spyOn>;

  beforeEach(() => {
    debugSpy = vi.spyOn(console, "debug").mockImplementation(() => {});
  });

  afterEach(() => {
    debugSpy.mockRestore();
  });

  it("does not flash rim; logs unknown id for modified after removal", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const flash = flashSpy(g);
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
    expect(map.has("raw123")).toBe(true);

    g.ingestDelta({ type: "node_removed", node_id: "raw123" });

    expect(fade).toHaveBeenCalledTimes(1);
    expect(map.has("raw123")).toBe(false);

    g.ingestDelta({ type: "node_modified", node_id: "raw123" });

    expect(flash).not.toHaveBeenCalled();
    expect(debugSpy).toHaveBeenCalledWith(
      "[t2-slice3] node_modified for unknown id",
      "raw123"
    );
  });
});
