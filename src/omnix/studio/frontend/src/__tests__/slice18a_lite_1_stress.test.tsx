import { describe, expect, it } from "vitest";
import {
  detectGalaxyStressTier,
  STRESS_TIER_TARGETS,
} from "@/components/Graph/galaxyStressHarness";
import { generateStressGraph } from "@/components/Graph/syntheticStressGraph";

function mockWindow(url: string): Window {
  const u = new URL(url, "http://127.0.0.1:7777");
  return {
    location: {
      search: u.search,
      hash: u.hash,
    },
  } as unknown as Window;
}

describe("slice 18a-lite.1 stress harness", () => {
  describe("detectGalaxyStressTier", () => {
    it("returns null for empty query", () => {
      expect(detectGalaxyStressTier(mockWindow("http://127.0.0.1:7777/"))).toBe(
        null
      );
    });

    it("parses ?stress=5k", () => {
      expect(
        detectGalaxyStressTier(mockWindow("http://127.0.0.1:7777/?stress=5k"))
      ).toBe("5k");
    });

    it("parses ?stress=50k", () => {
      expect(
        detectGalaxyStressTier(
          mockWindow("http://127.0.0.1:7777/?foo=1&stress=50k")
        )
      ).toBe("50k");
    });

    it("returns null for invalid stress value", () => {
      expect(
        detectGalaxyStressTier(
          mockWindow("http://127.0.0.1:7777/?stress=invalid")
        )
      ).toBe(null);
    });

    it("parses hash-router query #/foo?stress=15k", () => {
      expect(
        detectGalaxyStressTier(
          mockWindow("http://127.0.0.1:7777/#/galaxy?stress=15k")
        )
      ).toBe("15k");
    });

    it("search wins when both have stress (combined URLSearchParams order)", () => {
      expect(
        detectGalaxyStressTier(
          mockWindow("http://127.0.0.1:7777/?stress=5k#/p?stress=50k")
        )
      ).toBe("5k");
    });
  });

  describe("generateStressGraph", () => {
    it("hits target node counts per tier", () => {
      (["5k", "15k", "50k"] as const).forEach((tier) => {
        const g = generateStressGraph(tier);
        const expected = STRESS_TIER_TARGETS[tier];
        expect(g.nodes.length).toBe(
          expected.directories * expected.filesPerDir
        );
        expect(g.fromStress).toBe(true);
      });
    });

    it("is deterministic per tier", () => {
      const a = generateStressGraph("50k");
      const b = generateStressGraph("50k");
      expect(a.nodes[0]).toEqual(b.nodes[0]);
      expect(a.links.length).toBe(b.links.length);
    });

    it("differs across tiers", () => {
      const a = generateStressGraph("5k");
      const b = generateStressGraph("15k");
      expect(a.nodes[0].id).not.toBe(b.nodes[0].id);
    });

    it("uses links array and valid edge endpoints", () => {
      const g = generateStressGraph("5k");
      const ids = new Set(g.nodes.map((n) => n.id as string));
      for (const e of g.links) {
        expect(ids.has(e.source)).toBe(true);
        expect(ids.has(e.target)).toBe(true);
      }
    });
  });
});
