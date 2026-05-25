# OMNIX GitHub App — Shape C

Thin Probot-based webhook + PR surface for OMNIX behavioral replication.

The app dispatches to Shape A's cloud orchestrator. It does **not** replicate
OMNIX core logic in TypeScript.

## Layout

```
src/
  index.ts                  bootstrap: fastify + probot
  config.ts                 environment loader
  cloud_client.ts           Shape A HTTP client
  quota.ts                  freemium tier policy
  tenant.ts                 installation -> tenant resolution
  handlers/
    push.ts                 push -> Shape A startJob + check run
    pr_comment.ts           "/omnix replicate" slash command
    installation.ts         installation.created -> tenant provisioning
    job_complete.ts         HMAC-signed callback from Shape A: opens PR
```

## Development

```
cp .env.example .env
# Fill APP_ID / PRIVATE_KEY / WEBHOOK_SECRET from your GitHub App settings
# Set OMNIX_CLOUD_API_URL to your local or staging Shape A endpoint

npm install
npm run dev
# Use smee.io for webhook delivery if you don't have public ingress
```

## Permissions (minimum)

- `contents:read`
- `pull_requests:write`
- `checks:write`
- `metadata:read`

## Subscribed events

- `push`
- `pull_request`
- `issue_comment`
- `installation`
- `installation_repositories`

## Deploy

```bash
docker build -t omnix-github-app:dev .
docker run --env-file .env -p 3000:3000 omnix-github-app:dev
```
