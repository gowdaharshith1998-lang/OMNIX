import Fastify from "fastify";
import { createNodeMiddleware, createProbot, type Probot } from "probot";

import { config } from "./config.js";
import { registerInstallationHandler } from "./handlers/installation.js";
import { registerJobCompleteRoute } from "./handlers/job_complete.js";
import { registerPrCommentHandler } from "./handlers/pr_comment.js";
import { registerPushHandler } from "./handlers/push.js";

async function main(): Promise<void> {
  const probot = createProbot({
    overrides: {
      appId: config.appId(),
      privateKey: config.privateKey(),
      secret: config.webhookSecret(),
    },
  });

  // probot v13: createNodeMiddleware takes an ApplicationFunction (the same
  // shape probot.load expects), not the Probot instance. Define once, share
  // between probot.load (so handlers register) and the middleware factory
  // (so webhook deliveries fan out through the same handler graph).
  const appFn = (app: Probot): void => {
    registerPushHandler(app);
    registerPrCommentHandler(app);
    registerInstallationHandler(app);
  };

  await probot.load(appFn);

  const fastify = Fastify({ logger: { level: config.logLevel() } });

  // Mount the Probot webhook receiver alongside our own /webhooks/job-complete.
  const probotMiddleware = createNodeMiddleware(appFn, {
    probot,
    webhooksPath: "/api/github/webhooks",
  });
  fastify.all("/api/github/webhooks", (req, reply) => probotMiddleware(req.raw, reply.raw));

  // Liveness probe for container orchestration (HEALTHCHECK / k8s).
  fastify.get("/health", async () => ({ status: "ok" }));

  registerJobCompleteRoute(fastify, probot);

  await fastify.listen({ port: config.port(), host: "0.0.0.0" });
  fastify.log.info({ port: config.port() }, "OMNIX GitHub App ready");
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error("fatal:", err);
  process.exit(1);
});
