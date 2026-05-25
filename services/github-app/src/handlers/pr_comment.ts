import type { Probot } from "probot";
import { CloudClient } from "../cloud_client.js";
import { resolveTenant } from "../tenant.js";

const SLASH = /^\/omnix\s+replicate(\s+([\w-/.]+))?\s*$/;

export function registerPrCommentHandler(app: Probot): void {
  app.on("issue_comment.created", async (ctx) => {
    if (!ctx.payload.issue.pull_request) return;
    const match = SLASH.exec(ctx.payload.comment.body.trim());
    if (!match) return;

    const installationId = ctx.payload.installation?.id;
    if (!installationId) return;

    const repo = ctx.payload.repository;
    const prNumber = ctx.payload.issue.number;

    const tenant = await resolveTenant(installationId);
    const client = new CloudClient();
    try {
      const job = await client.startJob(
        {
          source: {
            type: "github",
            repo: repo.full_name,
            sha: "PR_HEAD",
            installation_id: installationId,
            ref: `refs/pull/${prNumber}/head`,
          },
          project_slug: match[2],
        },
        tenant,
      );
      await ctx.octokit.issues.createComment({
        owner: repo.owner.login,
        repo: repo.name,
        issue_number: prNumber,
        body:
          `OMNIX replication queued. Job: \`${job.job_id}\`\n\n` +
          `Live progress: ${client["baseUrl"]}/ws/jobs/${job.job_id}`,
      });
    } catch (err) {
      ctx.log.error({ err }, "slash dispatch failed");
      await ctx.octokit.issues.createComment({
        owner: repo.owner.login,
        repo: repo.name,
        issue_number: prNumber,
        body: `OMNIX dispatch failed: ${(err as Error).message}`,
      });
    }
  });
}

export const _SLASH_REGEX_FOR_TESTS = SLASH;
