import { describe, expect, it } from "vitest";
import { ACTION_REGISTRY } from "./registry";

describe("ACTION_REGISTRY", () => {
  it("contains the final slice 15.3 action set", () => {
    expect(Object.keys(ACTION_REGISTRY).sort()).toEqual([
      "bugs.explain_finding",
      "rightrail.new_agent",
      "xray.agent.explain_selection",
      "xray.diagnostics.dark_matter.investigate",
      "xray.diagnostics.entanglement.explain",
      "xray.diagnostics.god_file.split",
      "xray.diagnostics.high_complexity.extract",
      "xray.diagnostics.high_fan_in.versioned_interfaces",
      "xray.diagnostics.high_fan_out.facade",
      "xray.diagnostics.orphan_module.investigate",
    ]);
  });

  it("assigns impact tools to selection explanation", () => {
    const d = ACTION_REGISTRY["xray.agent.explain_selection"]({
      workspaceId: "wid",
      projectId: "pid",
      selectedNode: {
        id: "a.py::foo",
        name: "foo",
        type: "function",
        file_path: "a.py",
        line_start: 1,
        line_end: 3,
      },
    });
    expect(d.tools).toContain("find_callers");
    expect(d.tools).toContain("read_code_region");
    expect(d.workspaceId).toBe("wid");
  });
});
