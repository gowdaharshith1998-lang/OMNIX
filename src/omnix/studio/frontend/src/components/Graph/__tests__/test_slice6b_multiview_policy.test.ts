import { describe, expect, it, vi } from "vitest";
import viewerEngineSrc from "../viewerEngine.ts?raw";
import { StudioGraph } from "../StudioGraph";

vi.mock("../viewerEngine", () => ({
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
      _bornEdge?: ReturnType<typeof vi.fn>;
      _flashNodeRim?: ReturnType<typeof vi.fn>;
      _fadeAndRemoveNode?: ReturnType<typeof vi.fn>;
      _loadGraphFromData?: ReturnType<typeof vi.fn>;
      setViewContext?: (c: "planet-ready" | "non-planet") => void;
    };
  })._studio;
}

function minimalBootstrap(g: StudioGraph) {
  g.ingestDelta({ type: "bootstrap_start" });
  g.ingestDelta({
    type: "node_added",
    node: {
      id: "rawA",
      name: "alpha",
      type: "function",
      file_path: "shared.py",
      line_start: 1,
      line_end: 2,
    },
  });
  g.ingestDelta({
    type: "node_added",
    node: {
      id: "rawB",
      name: "beta",
      type: "function",
      file_path: "shared.py",
      line_start: 3,
      line_end: 4,
    },
  });
  g.ingestDelta({
    type: "bootstrap_complete",
    duration_ms: 0,
    total_nodes: 2,
    total_edges: 0,
  });
}

describe("slice 6b multi-view policy (Option A drop)", () => {
  it("live node_added is dropped when viewContext is non-planet", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    minimalBootstrap(g);
    const born = studioOf(g)._bornNode!;
    born.mockClear();

    g.ingestDelta({
      type: "node_added",
      node: {
        id: "rawC",
        name: "gamma",
        type: "function",
        file_path: "c.py",
        line_start: 1,
        line_end: 2,
      },
    });

    expect(born).not.toHaveBeenCalled();
  });

  it("live node_removed is dropped when viewContext is non-planet", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    minimalBootstrap(g);
    const fade = studioOf(g)._fadeAndRemoveNode!;
    fade.mockClear();

    g.ingestDelta({ type: "node_removed", node_id: "rawA" });

    expect(fade).not.toHaveBeenCalled();
    const map = (g as unknown as { _wsIdToSynthId: Map<string, string> })._wsIdToSynthId;
    expect(map.has("rawA")).toBe(true);
  });

  it("live node_modified is dropped when viewContext is non-planet", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    minimalBootstrap(g);
    const flash = studioOf(g)._flashNodeRim!;
    flash.mockClear();

    g.ingestDelta({ type: "node_modified", node_id: "rawA" });

    expect(flash).not.toHaveBeenCalled();
  });

  it("live edge_added is dropped when viewContext is non-planet", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    minimalBootstrap(g);
    const edge = studioOf(g)._bornEdge!;
    edge.mockClear();

    g.ingestDelta({
      type: "edge_added",
      edge: {
        id: 1,
        from_id: "rawA",
        to_id: "rawB",
        relationship: "CALLS",
      },
    });

    expect(edge).not.toHaveBeenCalled();
  });

  it("bootstrap_start + bootstrap_complete unaffected by viewContext (non-planet)", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    const load = studioOf(g)._loadGraphFromData!;
    load.mockClear();

    g.ingestDelta({ type: "bootstrap_start" });
    g.ingestDelta({
      type: "node_added",
      node: {
        id: "rawZ",
        name: "z",
        type: "function",
        file_path: "z.py",
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

    expect(load).toHaveBeenCalledTimes(1);
    const arg = load.mock.calls[0]![0] as { nodes: unknown[] };
    expect(arg.nodes.length).toBe(1);
  });

  it("viewContext transitions: non-planet → planet-ready → non-planet", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    minimalBootstrap(g);
    const st = studioOf(g);
    const born = st._bornNode!;
    born.mockClear();

    g.ingestDelta({
      type: "node_added",
      node: {
        id: "rawDropped",
        name: "dropped",
        type: "function",
        file_path: "d.py",
        line_start: 1,
        line_end: 2,
      },
    });
    expect(born).not.toHaveBeenCalled();

    st.setViewContext!("planet-ready");
    g.ingestDelta({
      type: "node_added",
      node: {
        id: "rawLate",
        name: "late",
        type: "function",
        file_path: "late.py",
        line_start: 1,
        line_end: 2,
      },
    });
    expect(born).toHaveBeenCalledTimes(1);

    born.mockClear();
    st.setViewContext!("non-planet");
    g.ingestDelta({
      type: "node_added",
      node: {
        id: "rawDrop",
        name: "drop",
        type: "function",
        file_path: "drop.py",
        line_start: 1,
        line_end: 2,
      },
    });
    expect(born).not.toHaveBeenCalled();
  });

  it("live delta during planet-ready creates planet cell as before", () => {
    const el = document.createElement("div");
    const g = new StudioGraph(el, {});
    minimalBootstrap(g);
    studioOf(g).setViewContext!("planet-ready");
    const born = studioOf(g)._bornNode!;
    born.mockClear();

    g.ingestDelta({
      type: "node_added",
      node: {
        id: "rawNew",
        name: "newfn",
        type: "function",
        file_path: "n.py",
        line_start: 1,
        line_end: 2,
      },
    });

    expect(born).toHaveBeenCalledTimes(1);
    const map = (g as unknown as { _wsIdToSynthId: Map<string, string> })._wsIdToSynthId;
    expect(map.get("rawNew")).toBe("n.py::newfn");
  });

  it("viewerEngine.ts?raw contract for setViewContext call sites", () => {
    expect(viewerEngineSrc).toContain("studio?.setViewContext?.('non-planet')");
    expect(viewerEngineSrc).toContain("studio?.setViewContext?.('planet-ready')");
    const ttp = viewerEngineSrc.indexOf("function transitionToPlanet(fileData)");
    expect(ttp).toBeGreaterThan(-1);
    const delayed = viewerEngineSrc.indexOf(
      "planetCreateDelayed = gsap.delayedCall",
      ttp
    );
    expect(delayed).toBeGreaterThan(ttp);
    expect(viewerEngineSrc.slice(ttp, delayed)).not.toContain("setViewContext");
  });
});
