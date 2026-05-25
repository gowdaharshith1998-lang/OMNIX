import dotenv from "dotenv";

dotenv.config();

function required(name: string): string {
  const v = process.env[name];
  if (!v) {
    throw new Error(`required env not set: ${name}`);
  }
  return v;
}

function optional(name: string, def: string = ""): string {
  return process.env[name] ?? def;
}

export const config = {
  appId: () => required("APP_ID"),
  privateKey: () => required("PRIVATE_KEY").replace(/\\n/g, "\n"),
  webhookSecret: () => required("WEBHOOK_SECRET"),
  cloudApiUrl: () => optional("OMNIX_CLOUD_API_URL", "http://localhost:8080"),
  cloudApiKey: () => optional("OMNIX_CLOUD_API_KEY"),
  port: () => Number(optional("PORT", "3000")),
  logLevel: () => optional("LOG_LEVEL", "info"),
  freeTier: {
    reposLimit: Number(optional("FREE_TIER_REPOS_LIMIT", "1")),
    runsPerMonth: Number(optional("FREE_TIER_RUNS_PER_MONTH", "5")),
  },
  teamTier: {
    reposLimit: Number(optional("TEAM_TIER_REPOS_LIMIT", "10")),
  },
  stripe: {
    secretKey: () => optional("STRIPE_SECRET_KEY"),
    webhookSecret: () => optional("STRIPE_WEBHOOK_SECRET"),
  },
};
