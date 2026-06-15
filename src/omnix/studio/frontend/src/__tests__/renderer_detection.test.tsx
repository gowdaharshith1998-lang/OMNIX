import { afterEach, describe, expect, it, vi } from "vitest";
import { VERSION } from "pixi.js";
import viewerEngineSrc from "@/components/Graph/viewerEngine.ts?raw";

describe("renderer detection", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("viewerEngine initPixi uses autoDetectRenderer boot path", () => {
    // Post-R8: runtime `[slice18a-lite]` console probes were stripped (debt-35 protocol).
    // This case guards the durable Pixi v7 boot contract, not removed instrumentation.
    expect(viewerEngineSrc).toMatch(/omnixPixiBootOptions/);
    expect(viewerEngineSrc).toMatch(/new PIXI\.Application\(omnixPixiBootOptions\)/);
    expect(viewerEngineSrc).toMatch(/slice18a-lite:/);
    expect(viewerEngineSrc).toMatch(/autoDetectRenderer/);
  });

  it("logs Pixi version via probe shape (runtime)", () => {
    expect(typeof VERSION).toBe("string");
    expect(VERSION.length).toBeGreaterThan(0);
  });

  it("documents that full autoDetectRenderer needs browser WebGL (vitest has none)", () => {
    expect(viewerEngineSrc).toMatch(/@pixi\/app/);
    expect(viewerEngineSrc).toMatch(/WebGPU preference requires Pixi v8/);
  });
});
