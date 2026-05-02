import { afterEach, describe, expect, it, vi } from "vitest";
import { VERSION } from "pixi.js";
import viewerEngineSrc from "@/components/Graph/viewerEngine.ts?raw";

describe("slice 18a-lite renderer detection", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("viewerEngine initPixi documents autoDetectRenderer boot path and probe", () => {
    expect(viewerEngineSrc).toMatch(/\[slice18a-lite\] renderer/);
    expect(viewerEngineSrc).toMatch(/autoDetectRenderer/);
    expect(viewerEngineSrc).toMatch(/omnixPixiBootOptions/);
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
