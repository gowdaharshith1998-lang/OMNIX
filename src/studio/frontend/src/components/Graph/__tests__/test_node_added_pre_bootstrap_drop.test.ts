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

describe("node_added pre-bootstrap live path", () => {
  it("does not call _bornNode before bootstrap_complete", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const born = bornSpy(g);

    g.ingestDelta({
      type: "node_added",
      node: {
        id: "early",
        name: "e",
        type: "function",
        file_path: "e.py",
        line_start: 1,
        line_end: 1,
      },
    });

    expect(born).not.toHaveBeenCalled();
  });
});
