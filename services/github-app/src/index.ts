import Fastify from "fastify";
import { createNodeMiddleware, createProbot } from "probot";

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

  await probot.load((app) => {
    registerPushHandler(app);
    registerPrCommentHandler(app);
    registerInstallationHandler(app);
  });

  const fastify = Fastify({ logger: { level: config.logLevel() } });

  // Mount the Probot webhook receiver alongside our own /webhooks/job-complete.
  fastify.all("/api/github/webhooks", (req, reply) => {
    const middleware = createNodeMiddleware(probot, { webhooksPath: "/api/github/webhooks" });
    return middleware(req.raw, reply.raw);
  });

  registerJobCompleteRoute(fastify, probot);

  await fastify.listen({ port: config.port(), host: "0.0.0.0" });
  fastify.log.info({ port: config.port() }, "OMNIX GitHub App ready");
}

main().catch((err) => {
  // eslint-disable-next-line no-console
  console.error("fatal:", err);
  process.exit(1);
});
