import { describe, expect, it } from "vitest";
import viewerEngineSrc from "../viewerEngine.ts?raw";

/**
 * Regression: _bornEdge must rebind d3.forceLink after pushing onto
 * planetLayer._edges (slice 6a).
 */
describe("viewerEngine _bornEdge d3 link force rebind", () => {
  it("contains push then force('link').links(edges).alpha(0.3).restart()", () => {
    expect(viewerEngineSrc).toMatch(/studio\._bornEdge\s*=\s*function/);
    expect(viewerEngineSrc).toMatch(/edges\.push\(/);
    expect(viewerEngineSrc).toMatch(
      /planetLayer\._sim\.force\('link'\)\.links\(edges\)/
    );
    expect(viewerEngineSrc).toMatch(/planetLayer\._sim\.alpha\(0\.3\)\.restart\(\)/);
  });
});
