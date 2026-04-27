import { describe, expect, it } from "vitest";
import {
  recordFromGraphPayload,
  wsEdgeToLinkShape,
  wsNodeToViewerShape,
} from "@/lib/graphNode";

/** DB-style WS function id (does not match T1 id; bridge synthesizes path::name). */
const sampleWsFunction = {
  id: "apps/foo.py::function::bar",
  name: "bar",
  type: "function",
  file_path: "apps/foo.py",
  line_start: 10,
  line_end: 20,
  metadata: {},
};

const sampleWsFile = {
  id: "apps/foo.py",
  name: "foo.py",
  type: "file",
  file_path: "apps/foo.py",
  line_start: 1,
  line_end: 1,
  metadata: {},
};

/** Mirrors `_edge_dict` / `msg_edge_added.edge`. */
const sampleWsEdge = {
  id: 42,
  source_id: "apps/foo.py::function::bar",
  target_id: "apps/foo.py::function::baz",
  relationship: "CALLS",
  metadata: {},
};

describe("payload shape compatibility (WS → viewerEngine)", () => {
  it("function nodes: T1-style id, file, val, color, and ws_id in metadata", () => {
    const v = wsNodeToViewerShape(sampleWsFunction);
    expect(v.id).toBe("apps/foo.py::bar");
    expect(v.id).toMatch(/::bar$/);
    expect(v.file).toBe("apps/foo.py");
    expect(v.val).toBe(2);
    expect(v.color).toBe("#4ade80");
    expect((v.metadata as Record<string, unknown>).ws_id).toBe(
      "apps/foo.py::function::bar"
    );
    expect(v.line).toBe(10);

    const rec = recordFromGraphPayload(v as Record<string, unknown>);
    expect(rec).not.toBeNull();
    expect(rec?.id).toBe("apps/foo.py::bar");
    expect(rec?.file_path).toBe("apps/foo.py");
    expect(rec?.line_start).toBe(10);
    expect(rec?.line_end).toBe(20);
  });

  it("file nodes: id === path, val 99, file color", () => {
    const v = wsNodeToViewerShape(sampleWsFile);
    expect(v.id).toBe("apps/foo.py");
    expect(v.id).toBe(sampleWsFile.file_path);
    expect(v.val).toBe(99);
    expect(v.color).toBe("#3b82f6");
    expect(v.file).toBe("apps/foo.py");
    expect((v.metadata as Record<string, unknown>).ws_id).toBe("apps/foo.py");
  });

  it("edges map to links with id, source, target, type", () => {
    const link = wsEdgeToLinkShape(sampleWsEdge);
    expect(link).toEqual({
      id: sampleWsEdge.id,
      source: sampleWsEdge.source_id,
      target: sampleWsEdge.target_id,
      type: "CALLS",
    });
  });
});
