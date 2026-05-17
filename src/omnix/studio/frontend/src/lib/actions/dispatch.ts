import {
  listProviderKeys,
  type ProviderKeyMetadata,
} from "@/lib/providersApi";
import type { ActionDescriptor, ActionResult, ToolStep } from "./types";

const jsonHeaders = { "Content-Type": "application/json" };

export class NoKeyRegisteredError extends Error {
  provider: string;

  constructor(provider: string) {
    super(`no key registered for ${provider}`);
    this.name = "NoKeyRegisteredError";
    this.provider = provider;
  }
}

export class DispatchError extends Error {
  result: ActionResult;

  constructor(result: ActionResult) {
    const trimmed = result.errorMessage?.trim();
    super(
      trimmed ||
        (result.provider
          ? `${result.provider}: dispatch failed — check the response details below.`
          : "dispatch failed — check the response details below."),
    );
    this.name = "DispatchError";
    this.result = result;
  }
}

function providerMatches(key: ProviderKeyMetadata, provider: string) {
  return key.provider === provider;
}

export async function resolveProviderForDescriptor(
  descriptor: ActionDescriptor
): Promise<string> {
  const keys = await listProviderKeys(descriptor.projectId);
  const projectKeys = keys.filter((k) =>
    descriptor.projectId ? k.scope === "project" && k.project_id === descriptor.projectId : false
  );
  const ordered = [...projectKeys, ...keys.filter((k) => k.scope === "global")];
  if (descriptor.provider) {
    if (!ordered.some((key) => providerMatches(key, descriptor.provider as string))) {
      throw new NoKeyRegisteredError(descriptor.provider);
    }
    return descriptor.provider;
  }
  const first = ordered[0];
  if (!first) throw new NoKeyRegisteredError("provider");
  return first.provider;
}

export async function dispatchAction(
  descriptor: ActionDescriptor,
  signal?: AbortSignal
): Promise<ActionResult> {
  const provider = await resolveProviderForDescriptor(descriptor);
  const response = await fetch("/api/action/dispatch", {
    method: "POST",
    headers: jsonHeaders,
    signal,
    body: JSON.stringify({
      descriptor_id: descriptor.id,
      prompt: descriptor.prompt,
      provider,
      model: descriptor.model,
      system_prompt: descriptor.systemPrompt,
      project_id: descriptor.projectId,
      workspace_id: descriptor.workspaceId,
      tools: descriptor.tools ?? [],
      tool_args: descriptor.toolArgs ?? {},
    }),
  });
  if (response.status === 400) {
    const body = (await response.json()) as { error?: string; provider?: string };
    if (body.error === "no_key_registered") {
      throw new NoKeyRegisteredError(body.provider || provider);
    }
  }
  if (!response.ok) {
    throw new Error(await response.text());
  }
  const raw = (await response.json()) as {
    ok: boolean;
    text?: string;
    provider?: string;
    model?: string;
    tokens_in?: number;
    tokens_out?: number;
    latency_ms?: number;
    receipt_id?: string;
    error?: string;
    error_class?: string;
    error_message?: string;
    http_status?: number | null;
    retryable?: boolean;
    tool_steps?: ToolStep[];
    cost_cap_triggered?: boolean;
    iterations?: number;
    capped?: boolean;
    cap_reason?: string | null;
  };
  const result: ActionResult = {
    ok: Boolean(raw.ok),
    text: raw.text || "",
    provider: raw.provider || provider,
    model: raw.model || descriptor.model || "",
    tokensIn: Number(raw.tokens_in || 0),
    tokensOut: Number(raw.tokens_out || 0),
    latencyMs: Number(raw.latency_ms || 0),
    receiptId: raw.receipt_id,
    error: raw.error,
    errorClass: raw.error_class || raw.error,
    errorMessage: raw.error_message,
    httpStatus:
      typeof raw.http_status === "number"
        ? raw.http_status
        : raw.http_status == null
          ? raw.http_status
          : Number(raw.http_status),
    retryable: Boolean(raw.retryable),
    toolSteps: Array.isArray(raw.tool_steps) ? raw.tool_steps : [],
    costCapTriggered: Boolean(raw.cost_cap_triggered),
    iterations: Number(raw.iterations ?? 0),
    capped: Boolean(raw.capped),
    capReason:
      typeof raw.cap_reason === "string" || raw.cap_reason == null
        ? raw.cap_reason
        : String(raw.cap_reason),
  };
  if (!result.ok) throw new DispatchError(result);
  return result;
}
