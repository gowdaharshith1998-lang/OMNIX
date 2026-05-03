const jsonHeaders = { "Content-Type": "application/json" };

export type DetectionResult = {
  provider: string;
  confidence: number;
  method: string;
};

export type ProviderKeyMetadata = {
  id: string;
  provider: string;
  display_name?: string;
  scope: "global" | "project";
  fingerprint: string;
  registered_at: string;
  project_id?: string | null;
  custom_base_url?: string | null;
  custom_model?: string | null;
};

export async function detectProvider(
  rawKey: string,
  customBaseUrl?: string
): Promise<DetectionResult> {
  const r = await fetch("/api/providers/detect", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({ raw_key: rawKey, custom_base_url: customBaseUrl || undefined }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<DetectionResult>;
}

export async function listProviderKeys(): Promise<ProviderKeyMetadata[]> {
  const r = await fetch("/api/providers/keys");
  if (!r.ok) throw new Error("list provider keys");
  const j = (await r.json()) as { keys: ProviderKeyMetadata[] };
  return j.keys;
}

export async function registerProviderKey(args: {
  rawKey: string;
  scope: "global" | "project";
  projectId?: string;
  overrideProvider?: string;
  customBaseUrl?: string;
  customModel?: string;
}): Promise<ProviderKeyMetadata> {
  const r = await fetch("/api/providers/keys", {
    method: "POST",
    headers: jsonHeaders,
    body: JSON.stringify({
      raw_key: args.rawKey,
      scope: args.scope,
      project_id: args.projectId,
      override_provider: args.overrideProvider,
      custom_base_url: args.customBaseUrl,
      custom_model: args.customModel,
    }),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<ProviderKeyMetadata>;
}

export async function deleteProviderKey(
  id: string
): Promise<{ deleted: boolean; reason?: string }> {
  const r = await fetch(`/api/providers/keys/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json() as Promise<{ deleted: boolean; reason?: string }>;
}
