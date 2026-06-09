import { createHmac, timingSafeEqual } from "node:crypto";
import type { FastifyInstance, FastifyRequest } from "fastify";
import type { Probot } from "probot";

import { config } from "../config.js";
import type { JobCompleteWebhook, ReplicatedUnit } from "../cloud_client.js";

const CHECK_RUN_NAME = "OMNIX equivalence verification";

function verifyHmac(raw: Buffer, signatureHeader: string | undefined): boolean {
  if (!signatureHeader) return false;
  const expected = createHmac("sha256", config.webhookSecret())
    .update(raw)
    .digest("hex");
  const provided = signatureHeader.startsWith("sha256=")
    ? signatureHeader.slice(7)
    : signatureHeader;
  const eBuf = Buffer.from(expected);
  const pBuf = Buffer.from(provided);
  if (eBuf.length !== pBuf.length) return false;
  return timingSafeEqual(eBuf, pBuf);
}

export function registerJobCompleteRoute(fastify: FastifyInstance, probot: Probot): void {
  fastify.post(
    "/webhooks/job-complete",
    {
      config: { rawBody: true },
    },
    async (request: FastifyRequest, reply) => {
      const raw = (request as unknown as { rawBody?: Buffer }).rawBody;
      const sig = request.headers["x-omnix-signature"] as string | undefined;
      if (!raw || !verifyHmac(raw, sig)) {
        return reply.code(401).send({ detail: "invalid signature" });
      }
      const payload = JSON.parse(raw.toString()) as JobCompleteWebhook;
      validateJobCompletePayload(payload);
      const ok = await openReplicationPr(probot, payload);
      return reply.send({ ok });
    },
  );
}

async function openReplicationPr(
  probot: Probot,
  payload: JobCompleteWebhook,
): Promise<boolean> {
  const auth = await probot.auth(payload.installation_id);
  const [owner, repo] = splitRepo(payload.repo);

  const baseRef = await auth.repos.get({ owner, repo });
  const headSha = baseRef.data.default_branch;
  const branchName = sanitizeReplicationBranchName(payload.job_id);

  const baseRefData = await auth.git.getRef({
    owner,
    repo,
    ref: `heads/${headSha}`,
  });
  await auth.git.createRef({
    owner,
    repo,
    ref: `refs/heads/${branchName}`,
    sha: baseRefData.data.object.sha,
  });

  for (const unit of payload.units) {
    await auth.repos.createOrUpdateFileContents({
      owner,
      repo,
      path: validateTargetPath(unit.target_path),
      branch: branchName,
      message: `OMNIX: replicate ${unit.unit_id} -> ${unit.target_language}`,
      content: Buffer.from(unit.generated_code, "utf-8").toString("base64"),
    });
  }

  const body = renderPrBody(payload, payload.units);
  const pr = await auth.pulls.create({
    owner,
    repo,
    head: branchName,
    base: headSha,
    title: `OMNIX replication: ${payload.units.length} units to ${payload.units[0]?.target_language ?? "?"}`,
    body,
  });

  await auth.checks.create({
    owner,
    repo,
    name: CHECK_RUN_NAME,
    head_sha: pr.data.head.sha,
    status: "completed",
    conclusion: equivalenceConclusion(payload.units),
    output: {
      title: CHECK_RUN_NAME,
      summary: summarizeUnits(payload.units),
    },
  });

  return true;
}

function splitRepo(repoFullName: string): [string, string] {
  if (!/^[A-Za-z0-9_.-]+\/[A-Za-z0-9_.-]+$/.test(repoFullName)) {
    throw new Error("invalid repository name");
  }
  return repoFullName.split("/", 2) as [string, string];
}

export function sanitizeReplicationBranchName(jobId: string): string {
  const suffix = jobId.replace(/[^A-Za-z0-9_-]/g, "-").slice(0, 80);
  return `omnix/replicate/${suffix || "job"}`;
}

export function validateTargetPath(path: string): string {
  const normalized = path.replace(/\\/g, "/");
  const parts = normalized.split("/").filter((part) => part.length > 0);
  if (
    !normalized
    || normalized.startsWith("/")
    || /^[A-Za-z]:\//.test(normalized)
    || parts.length === 0
    || parts.includes("..")
    || parts.includes(".git")
  ) {
    throw new Error(`invalid target path: ${path}`);
  }
  const candidate = parts.join("/");
  const lower = candidate.toLowerCase();
  if (lower === ".github/workflows" || lower.startsWith(".github/workflows/")) {
    throw new Error("workflow file writes are not allowed");
  }
  return candidate;
}

export function validateJobCompletePayload(payload: JobCompleteWebhook): void {
  if (!Number.isInteger(payload.installation_id) || payload.installation_id <= 0) {
    throw new Error("invalid installation id");
  }
  splitRepo(payload.repo);
  for (const unit of payload.units) {
    validateTargetPath(unit.target_path);
  }
}

function summarizeUnits(units: ReplicatedUnit[]): string {
  const totals = units.reduce(
    (acc, u) => ({
      agreed: acc.agreed + u.daikon_invariants_agreed,
      violated: acc.violated + u.daikon_invariants_violated,
      scientist: acc.scientist + u.scientist_mismatches,
      diffy: acc.diffy + u.diffy_mismatches,
    }),
    { agreed: 0, violated: 0, scientist: 0, diffy: 0 },
  );
  return [
    `${units.length} units replicated`,
    `Daikon invariants agreed: ${totals.agreed}`,
    `Daikon invariants violated: ${totals.violated}`,
    `Scientist mismatches: ${totals.scientist}`,
    `Diffy mismatches: ${totals.diffy}`,
  ].join("\n");
}

function equivalenceConclusion(units: ReplicatedUnit[]): "success" | "failure" | "neutral" {
  for (const u of units) {
    if (u.daikon_invariants_violated > 0) return "failure";
    if (u.scientist_mismatches > 0) return "failure";
    if (u.diffy_mismatches > 0) return "failure";
  }
  return "success";
}

function renderPrBody(payload: JobCompleteWebhook, units: ReplicatedUnit[]): string {
  const target = units[0]?.target_language ?? "java21";
  const receipts = units
    .map((u) => `- [\`${u.unit_id}\`](${u.verifier_url}) — receipt ${u.receipt_id}`)
    .join("\n");

  return [
    `# OMNIX replication — ${units.length} units to ${target}`,
    "",
    "## Equivalence proof summary",
    summarizeUnits(units).split("\n").map((s) => `- ${s}`).join("\n"),
    "",
    "## Signed receipts",
    receipts,
    "",
    "## Verification footer",
    "All output cryptographically signed with **ML-DSA-65 (FIPS 204, post-quantum)**. Verify independently with the URLs above or via `omnix verify <receipt-url>`.",
  ].join("\n");
}
