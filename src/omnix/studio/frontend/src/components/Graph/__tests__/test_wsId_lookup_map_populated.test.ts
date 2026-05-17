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

describe("_wsIdToSynthId map after bootstrap", () => {
  it("stores ws_id -> synthesized id for each bridged node", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});

    g.ingestDelta({ type: "bootstrap_start" });
    const specs = [
      { wsId: "a", name: "fa", path: "fa.py" },
      { wsId: "b", name: "fb", path: "fb.py" },
      { wsId: "c", name: "fc", path: "fc.py" },
    ];
    for (const s of specs) {
      g.ingestDelta({
        type: "node_added",
        node: {
          id: s.wsId,
          name: s.name,
          type: "function",
          file_path: s.path,
          line_start: 1,
          line_end: 1,
        },
      });
    }
    g.ingestDelta({
      type: "bootstrap_complete",
      duration_ms: 0,
      total_nodes: 3,
      total_edges: 0,
    });

    const map = (g as unknown as { _wsIdToSynthId: Map<string, string> })._wsIdToSynthId;
    expect(map.get("a")).toBe("fa.py::fa");
    expect(map.get("b")).toBe("fb.py::fb");
    expect(map.get("c")).toBe("fc.py::fc");
  });
});
