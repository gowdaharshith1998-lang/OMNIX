import type { Probot } from "probot";
import { provisionTenantForInstallation } from "../tenant.js";

export function registerInstallationHandler(app: Probot): void {
  app.on("installation.created", async (ctx) => {
    const installation = ctx.payload.installation;
    await provisionTenantForInstallation(installation.id, installation.account?.login ?? "unknown");
    ctx.log.info({ installationId: installation.id }, "tenant provisioned");
  });

  app.on("installation_repositories.added", async (ctx) => {
    const installationId = ctx.payload.installation.id;
    const added = ctx.payload.repositories_added.map((r) => r.full_name);
    ctx.log.info({ installationId, added }, "repos added to installation");
  });
}
