import { describe, expect, it, vi } from "vitest";
import { isT1Mode } from "@/lib/t1Mode";
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

describe("T1 mode guard", () => {
  it("does not run live bootstrap rebuild when isT1Mode is true; loadInitial remains the static path", () => {
    vi.mocked(isT1Mode).mockReturnValue(true);
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const spy = loadSpy(g);

    g.ingestDelta({ type: "bootstrap_start" });
    for (let i = 0; i < 5; i++) {
      g.ingestDelta({
        type: "node_added",
        node: {
          id: `n${i}`,
          name: `x${i}`,
          type: "function",
          file_path: "a.py",
          line_start: 1,
          line_end: 1,
        },
      });
    }
    g.ingestDelta({
      type: "bootstrap_complete",
      duration_ms: 0,
      total_nodes: 5,
      total_edges: 0,
    });
    expect(spy).not.toHaveBeenCalled();

    g.loadInitial([], [], {});
    expect(spy).toHaveBeenCalledTimes(1);
  });
});
