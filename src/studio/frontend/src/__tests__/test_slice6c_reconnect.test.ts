import { describe, expect, it, vi } from "vitest";
import { StudioGraph } from "../components/Graph/StudioGraph";

vi.mock("../components/Graph/viewerEngine", () => ({
  installOmnixViewerEngine: (studio: {
    _loadGraphFromData?: ReturnType<typeof vi.fn>;
    _destroy?: ReturnType<typeof vi.fn>;
    _bornNode?: ReturnType<typeof vi.fn>;
    _bornEdge?: ReturnType<typeof vi.fn>;
    _flashNodeRim?: ReturnType<typeof vi.fn>;
    _fadeAndRemoveNode?: ReturnType<typeof vi.fn>;
  }) => {
    studio._loadGraphFromData = vi.fn();
    studio._destroy = vi.fn();
    studio._bornNode = vi.fn(() => true);
    studio._bornEdge = vi.fn(() => true);
    studio._flashNodeRim = vi.fn();
    studio._fadeAndRemoveNode = vi.fn();
  },
}));

vi.mock("@/lib/t1Mode", () => ({
  isT1Mode: vi.fn(() => false),
}));

function studioOf(g: StudioGraph) {
  return (g as unknown as {
    _studio: {
      _bornNode?: ReturnType<typeof vi.fn>;
      _flashNodeRim?: ReturnType<typeof vi.fn>;
      _loadGraphFromData?: ReturnType<typeof vi.fn>;
      setViewContext?: (c: "planet-ready" | "non-planet") => void;
    };
  })._studio;
}

function bootBuf(g: StudioGraph) {
  return (g as unknown as {
    _bootstrapBuffer: {
      nodes: unknown[];
      started: boolean;
      completed: boolean;
      snapshotDone: boolean;
    };
  })._bootstrapBuffer;
}

function fnNode(
  id: string,
  name: string,
  filePath: string
): Record<string, unknown> {
  return {
    id,
    name,
    type: "function",
    file_path: filePath,
    line_start: 1,
    line_end: 2,
  };
}

function planetReady(g: StudioGraph) {
  studioOf(g).setViewContext!("planet-ready");
}

describe("slice 6c reconnect policy (Option B — mid-session bootstrap)", () => {
  it("mid-session bootstrap_start resets _bootstrapBuffer cleanly after previous bootstrap_complete", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const load = studioOf(g)._loadGraphFromData!;

    g.ingestDelta({ type: "bootstrap_start" });
    g.ingestDelta({ type: "node_added", node: fnNode("n1", "a", "f.py") });
    g.ingestDelta({ type: "node_added", node: fnNode("n2", "b", "f.py") });
    g.ingestDelta({ type: "node_added", node: fnNode("n3", "c", "f.py") });
    g.ingestDelta({
      type: "bootstrap_complete",
      duration_ms: 0,
      total_nodes: 3,
      total_edges: 0,
    });

    expect(load).toHaveBeenCalledTimes(1);

    g.ingestDelta({ type: "bootstrap_start" });
    const buf = bootBuf(g);
    expect(buf.nodes.length).toBe(0);
    expect(buf.completed).toBe(false);
    expect(buf.snapshotDone).toBe(false);

    g.ingestDelta({ type: "node_added", node: fnNode("x1", "x", "g.py") });
    g.ingestDelta({ type: "node_added", node: fnNode("y1", "y", "g.py") });
    g.ingestDelta({
      type: "bootstrap_complete",
      duration_ms: 0,
      total_nodes: 2,
      total_edges: 0,
    });

    expect(load).toHaveBeenCalledTimes(2);
    const second = load.mock.calls[1]![0] as { nodes: unknown[] };
    expect(second.nodes.length).toBe(2);
  });

  it("live deltas during mid-session bootstrap window: pre-complete drops apply; planet gate inactive until bootstrap completes", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const load = studioOf(g)._loadGraphFromData!;
    const born = studioOf(g)._bornNode!;
    const flash = studioOf(g)._flashNodeRim!;

    g.ingestDelta({ type: "bootstrap_start" });
    g.ingestDelta({ type: "node_added", node: fnNode("k1", "k", "k.py") });
    g.ingestDelta({
      type: "bootstrap_complete",
      duration_ms: 0,
      total_nodes: 1,
      total_edges: 0,
    });

    planetReady(g);
    born.mockClear();
    flash.mockClear();

    g.ingestDelta({ type: "bootstrap_start" });
    expect(bootBuf(g).completed).toBe(false);

    // Slice 5 path: live node_added while !completed is dropped (not born).
    g.ingestDelta({
      type: "node_added",
      node: fnNode("live1", "live", "live.py"),
    });
    expect(born).not.toHaveBeenCalled();

    // node_modified: slice 6b _shouldDropLivePlanetDelta requires completed===true,
    // so mid-bootstrap uses lookup; unknown ws id → no flash (safe during rebootstrap).
    g.ingestDelta({ type: "node_modified", node_id: "no-such-ws-yet" });
    expect(flash).not.toHaveBeenCalled();

    g.ingestDelta({
      type: "bootstrap_complete",
      duration_ms: 0,
      total_nodes: 1,
      total_edges: 0,
    });

    expect(load).toHaveBeenCalledTimes(2);
  });

  it("_wsIdToSynthId rebuilds correctly after mid-session rebootstrap", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});

    g.ingestDelta({ type: "bootstrap_start" });
    g.ingestDelta({ type: "node_added", node: fnNode("a", "fa", "f.py") });
    g.ingestDelta({ type: "node_added", node: fnNode("b", "fb", "f.py") });
    g.ingestDelta({ type: "node_added", node: fnNode("c", "fc", "f.py") });
    g.ingestDelta({
      type: "bootstrap_complete",
      duration_ms: 0,
      total_nodes: 3,
      total_edges: 0,
    });

    const map1 = (g as unknown as { _wsIdToSynthId: Map<string, string> })
      ._wsIdToSynthId;
    expect(map1.size).toBe(3);
    const synthA = map1.get("a");
    expect(synthA).toBe("f.py::fa");

    g.ingestDelta({ type: "bootstrap_start" });
    g.ingestDelta({ type: "node_added", node: fnNode("x", "fx", "g.py") });
    g.ingestDelta({ type: "node_added", node: fnNode("y", "fy", "h.py") });
    g.ingestDelta({
      type: "bootstrap_complete",
      duration_ms: 0,
      total_nodes: 2,
      total_edges: 0,
    });

    const map2 = (g as unknown as { _wsIdToSynthId: Map<string, string> })
      ._wsIdToSynthId;
    expect(map2.size).toBe(2);
    expect(map2.has("a")).toBe(false);
    expect(map2.has("b")).toBe(false);
    expect(map2.has("c")).toBe(false);
    expect(map2.get("x")).toBe("g.py::fx");
    expect(map2.get("y")).toBe("h.py::fy");
    expect(map2.get("x")).not.toBe(synthA);
  });
});
