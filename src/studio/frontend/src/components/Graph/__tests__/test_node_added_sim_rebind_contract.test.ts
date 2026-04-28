import { describe, expect, it } from "vitest";
import viewerEngineSrc from "../viewerEngine.ts?raw";

/**
 * Regression: _bornNode must push pnRef, then rebind d3.forceSimulation to
 * planetLayer._nodes so the newcomer participates in layout (slice 5).
 */
describe("viewerEngine _bornNode d3 simulation rebind", () => {
  it("contains push then _sim.nodes(_nodes).alpha(0.3).restart()", () => {
    expect(viewerEngineSrc).toMatch(/planetLayer\._nodes\.push\(pnRef\)/);
    expect(viewerEngineSrc).toMatch(
      /planetLayer\._sim\.nodes\(planetLayer\._nodes\)\.alpha\(0\.3\)\.restart\(\)/
    );
  });
});
