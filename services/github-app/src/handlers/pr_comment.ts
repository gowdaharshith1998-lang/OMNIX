import type { Probot } from "probot";
import { CloudClient } from "../cloud_client.js";
import { quota } from "../quota.js";
import { resolveTenant, resolveTier } from "../tenant.js";

const SLASH = /^\/omnix\s+replicate(\s+([\w-/.]+))?\s*$/;
const TRUSTED_AUTHOR_ASSOCIATIONS = new Set(["OWNER", "MEMBER", "COLLABORATOR"]);

export function isTrustedSlashCommandAuthor(
  authorAssociation: string | undefined,
): boolean {
  return Boolean(
    authorAssociation && TRUSTED_AUTHOR_ASSOCIATIONS.has(authorAssociation),
  );
}

export function registerPrCommentHandler(app: Probot): void {
  app.on("issue_comment.created", async (ctx) => {
    if (!ctx.payload.issue.pull_request) return;
    const match = SLASH.exec(ctx.payload.comment.body.trim());
    if (!match) return;

    const installationId = ctx.payload.installation?.id;
    if (!installationId) return;

    const repo = ctx.payload.repository;
    const prNumber = ctx.payload.issue.number;
    if (!isTrustedSlashCommandAuthor(ctx.payload.comment.author_association)) {
      ctx.log.warn(
        {
          user: ctx.payload.comment.user?.login,
          authorAssociation: ctx.payload.comment.author_association,
        },
        "skipping untrusted slash command",
      );
      await ctx.octokit.issues.createComment({
        owner: repo.owner.login,
        repo: repo.name,
        issue_number: prNumber,
        body: "OMNIX replication skipped: only repository owners, members, or collaborators may run this command.",
      });
      return;
    }

    const tenant = await resolveTenant(installationId);
    const tier = await resolveTier(installationId);
    const check = quota.check(installationId, tier);
    if (!check.allowed) {
      ctx.log.warn({ installationId, reason: check.reason }, "quota exceeded");
      await ctx.octokit.issues.createComment({
        owner: repo.owner.login,
        repo: repo.name,
        issue_number: prNumber,
        body: `OMNIX replication skipped: ${check.reason}`,
      });
      return;
    }

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
      quota.record(installationId);
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
