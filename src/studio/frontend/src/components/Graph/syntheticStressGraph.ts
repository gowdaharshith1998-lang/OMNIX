import type { GalaxyStressTier } from "./galaxyStressHarness";
import { STRESS_TIER_TARGETS } from "./galaxyStressHarness";

/** Viewer payload shape: matches post–wsNodeToViewerShape file nodes + links (not edges). */
export interface StressGraphPayload {
  nodes: Array<Record<string, unknown>>;
  links: Array<{
    id?: string | number;
    source: string;
    target: string;
    type: string;
  }>;
  stats: Record<string, unknown>;
  fromStress: true;
}

function makeRng(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 0xffffffff;
  };
}

const STRESS_SEEDS: Record<GalaxyStressTier, number> = {
  "5k": 0x0500_01,
  "15k": 0x1500_01,
  "50k": 0x5000_01,
};

const COLORS = ["#3b82f6", "#06b6d4", "#a855f7", "#f97316", "#4ade80"];

/**
 * Synthetic stress graph: file-typed nodes only; galaxy directories are derived from dirname(file).
 */
export function generateStressGraph(tier: GalaxyStressTier): StressGraphPayload {
  const cfg = STRESS_TIER_TARGETS[tier];
  const rng = makeRng(STRESS_SEEDS[tier]);

  const nodes: StressGraphPayload["nodes"] = [];
  const links: StressGraphPayload["links"] = [];

  for (let d = 0; d < cfg.directories; d++) {
    const dirPath = `synthetic/stress_${tier}/dir_${d}`;
    for (let f = 0; f < cfg.filesPerDir; f++) {
      const filePath = `${dirPath}/file_${f}.py`;
      const color = COLORS[(d + f) % COLORS.length];
      nodes.push({
        id: filePath,
        name: `file_${f}.py`,
        type: "file",
        file: filePath,
        line: 1,
        val: 99,
        color,
        line_start: 0,
        line_end: 0,
        metadata: {
          ws_id: filePath,
          original_id: filePath,
        },
      });

      if (f > 0 && rng() < 0.1) {
        const prevPath = `${dirPath}/file_${f - 1}.py`;
        links.push({
          source: filePath,
          target: prevPath,
          type: "IMPORTS",
        });
      }
    }
  }

  return {
    nodes,
    links,
    stats: {
      files: cfg.directories * cfg.filesPerDir,
      functions: 0,
      classes: 0,
      edges: links.length,
      dark_matter: 0,
      entangled: 0,
    },
    fromStress: true,
  };
}
