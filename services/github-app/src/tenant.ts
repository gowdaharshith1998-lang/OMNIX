/**
 * Tenant resolution for GitHub App installations.
 * In production this calls into Shape A's database. The stub returns a
 * deterministic tenant id derived from the installation id.
 */
import type { Tier } from "./quota.js";

const _tenants = new Map<number, string>();
const _tiers = new Map<number, Tier>();

export async function provisionTenantForInstallation(
  installationId: number,
  accountLogin: string,
): Promise<string> {
  const id = `gh-${installationId}-${accountLogin}`;
  _tenants.set(installationId, id);
  _tiers.set(installationId, "free");
  return id;
}

export async function resolveTenant(installationId: number): Promise<string> {
  const cached = _tenants.get(installationId);
  if (cached) return cached;
  // Lazy-provision unknown installations as free-tier.
  return provisionTenantForInstallation(installationId, "unknown");
}

export async function resolveTier(installationId: number): Promise<Tier> {
  return _tiers.get(installationId) ?? "free";
}

export function setTier(installationId: number, tier: Tier): void {
  _tiers.set(installationId, tier);
}

export function resetForTests(): void {
  _tenants.clear();
  _tiers.clear();
}
