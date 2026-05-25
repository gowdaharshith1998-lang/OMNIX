import { config } from "./config.js";

export type Tier = "free" | "team" | "enterprise";

export interface QuotaCheck {
  allowed: boolean;
  reason?: string;
  remaining?: number;
}

/**
 * Quota enforcement for the GitHub App (Phase C2 freemium).
 * Real implementation reads usage from the Shape A backend (Postgres).
 * This in-memory variant is the test+dev surface.
 */
export class QuotaTracker {
  private usage: Map<string, number> = new Map(); // installation_id -> runs this month

  check(installationId: number, tier: Tier): QuotaCheck {
    const key = String(installationId);
    const used = this.usage.get(key) ?? 0;

    if (tier === "free") {
      const limit = config.freeTier.runsPerMonth;
      if (used >= limit) {
        return {
          allowed: false,
          reason: `free tier limit reached: ${used}/${limit} runs this month`,
          remaining: 0,
        };
      }
      return { allowed: true, remaining: limit - used };
    }
    if (tier === "team") {
      return { allowed: true };
    }
    if (tier === "enterprise") {
      return { allowed: true };
    }
    return { allowed: false, reason: `unknown tier: ${tier as string}` };
  }

  record(installationId: number): void {
    const key = String(installationId);
    this.usage.set(key, (this.usage.get(key) ?? 0) + 1);
  }

  reset(installationId?: number): void {
    if (installationId === undefined) {
      this.usage.clear();
    } else {
      this.usage.delete(String(installationId));
    }
  }
}

export const quota = new QuotaTracker();
