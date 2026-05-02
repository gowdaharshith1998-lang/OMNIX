/**
 * Galaxy stress tier detection (?stress=5k|15k|50k). Supports query in search or hash.
 */

export type GalaxyStressTier = "5k" | "15k" | "50k";

/** Set once per session when synthetic stress graph loads; never cleared (A12). */
let activeGalaxyStressTier: GalaxyStressTier | null = null;

export function getActiveGalaxyStressTier(): GalaxyStressTier | null {
  return activeGalaxyStressTier;
}

export function activateGalaxyStressTier(tier: GalaxyStressTier): void {
  activeGalaxyStressTier = tier;
}

export function detectGalaxyStressTier(win: Window | undefined): GalaxyStressTier | null {
  if (typeof win === "undefined" || !win?.location) return null;

  const search = win.location.search ?? "";
  const hash = win.location.hash ?? "";
  const hashQuery = hash.includes("?") ? hash.slice(hash.indexOf("?")) : "";
  const combined = `${search}&${hashQuery.replace(/^\?/, "")}`;

  const params = new URLSearchParams(combined);
  const value = params.get("stress")?.toLowerCase().trim() ?? null;

  if (value === "5k" || value === "15k" || value === "50k") return value;
  return null;
}

/** Directory count × files per dir = raw file nodes (approximate totals in EARS). */
export const STRESS_TIER_TARGETS: Record<
  GalaxyStressTier,
  { directories: number; filesPerDir: number; totalNodes: number }
> = {
  "5k": { directories: 50, filesPerDir: 101, totalNodes: 5050 },
  "15k": { directories: 150, filesPerDir: 101, totalNodes: 15150 },
  "50k": { directories: 500, filesPerDir: 101, totalNodes: 50500 },
};
