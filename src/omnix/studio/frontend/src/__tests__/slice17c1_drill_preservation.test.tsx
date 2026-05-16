import { afterEach, describe, expect, it, vi } from "vitest";
import {
  resetStudioScopeForTests,
  setScope,
  setValidScopeIds,
  syncScopeFromViewer,
} from "@/store/studioScopeStore";

/**
 * slice17c1 R0/R1: canvas drill is synchronous in viewerEngine.onNodeClick → transitionToStar.
 * React only observes notifyViewerScope → syncScopeFromViewer; GraphCanvas must not reset
 * an in-progress star view when applying the same directory spec (viewerEngine guard).
 */
describe("slice17c1 drill preservation — scope probes + atom", () => {
  afterEach(() => {
    resetStudioScopeForTests();
    vi.restoreAllMocks();
  });

  it("setScope emits [slice17c1] atom set (programmatic breadcrumb path)", () => {
    const dbg = vi.spyOn(console, "debug").mockImplementation(() => {});
    setValidScopeIds(["repo", "pkg-parser"]);
    const ok = setScope("pkg-parser");
    expect(ok).toBe(true);
    expect(dbg).toHaveBeenCalledWith(
      "[slice17c1] atom set",
      expect.objectContaining({ path: "pkg-parser", source: "setScope" })
    );
  });

  it("syncScopeFromViewer emits [slice17c1] atom set (viewer notify path)", () => {
    const dbg = vi.spyOn(console, "debug").mockImplementation(() => {});
    setValidScopeIds(["repo", "pkg-parser"]);
    setScope("repo");
    dbg.mockClear();
    syncScopeFromViewer("pkg-parser", {
      pathPrefixForScope: () => "src/parser",
      selectedFilePath: () => null,
    });
    expect(dbg).toHaveBeenCalledWith(
      "[slice17c1] atom set",
      expect.objectContaining({ path: "pkg-parser", source: "syncScopeFromViewer" })
    );
  });
});
