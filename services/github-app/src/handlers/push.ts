import type { Context, Probot } from "probot";
import { CloudClient } from "../cloud_client.js";
import { quota } from "../quota.js";
import { resolveTenant, resolveTier } from "../tenant.js";

const CHECK_RUN_NAME = "OMNIX replication analysis";

export function registerPushHandler(app: Probot): void {
  app.on("push", async (ctx) => {
    if (!ctx.payload.repository) return;
    const installationId = ctx.payload.installation?.id;
    if (!installationId) return;

    // Only run on the repo's default branch by default. Slash-command path in
    // pr_comment.ts allows ad-hoc PR-scoped runs.
    const defaultBranch = ctx.payload.repository.default_branch;
    const ref = ctx.payload.ref;
    if (ref !== `refs/heads/${defaultBranch}`) {
      ctx.log.debug({ ref, defaultBranch }, "skipping non-default-branch push");
      return;
    }

    const tenant = await resolveTenant(installationId);
    const tier = await resolveTier(installationId);
    const check = quota.check(installationId, tier);
    if (!check.allowed) {
      ctx.log.warn({ installationId, reason: check.reason }, "quota exceeded");
      await postCheckRun(ctx, "completed", "neutral",
        `OMNIX skipped: ${check.reason}`);
      return;
    }

    await postCheckRun(ctx, "in_progress", undefined,
      "OMNIX replication analysis queued...");

    const client = new CloudClient();
    try {
      const job = await client.startJob(
        {
          source: {
            type: "github",
            repo: ctx.payload.repository.full_name,
            sha: ctx.payload.after,
            installation_id: installationId,
          },
        },
        tenant,
      );
      quota.record(installationId);
      ctx.log.info({ jobId: job.job_id }, "OMNIX job dispatched");
    } catch (err) {
      ctx.log.error({ err }, "OMNIX dispatch failed");
      await postCheckRun(ctx, "completed", "failure",
        `OMNIX dispatch failed: ${(err as Error).message}`);
    }
  });
}

async function postCheckRun(
  ctx: Context<"push">,
  status: "queued" | "in_progress" | "completed",
  conclusion: "success" | "failure" | "neutral" | "cancelled" | undefined,
  summary: string,
): Promise<void> {
  try {
    await ctx.octokit.checks.create({
      owner: ctx.payload.repository.owner.login,
      repo: ctx.payload.repository.name,
      name: CHECK_RUN_NAME,
      head_sha: ctx.payload.after,
      status,
      conclusion,
      output: {
        title: CHECK_RUN_NAME,
        summary,
      },
    });
  } catch (err) {
    ctx.log.warn({ err }, "check run create failed");
  }
}
