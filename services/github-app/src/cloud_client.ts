import { config } from "./config.js";

export type StartJobSource =
  | { type: "github"; repo: string; sha: string; installation_id: number; ref?: string }
  | { type: "tus"; upload_id: string }
  | { type: "git"; repo: string; ref?: string; token?: string };

export interface StartJobRequest {
  source: StartJobSource;
  target_language?: string;
  project_slug?: string;
}

export interface StartJobResponse {
  job_id: string;
  ws_url: string;
  state: string;
}

export interface JobCompleteWebhook {
  job_id: string;
  installation_id: number;
  repo: string;
  units: ReplicatedUnit[];
}

export interface ReplicatedUnit {
  unit_id: string;
  source_path: string;
  target_path: string;
  target_language: string;
  receipt_id: string;
  receipt_url: string;
  verifier_url: string;
  daikon_invariants_agreed: number;
  daikon_invariants_violated: number;
  scientist_mismatches: number;
  diffy_mismatches: number;
  generated_code: string;
}

/**
 * Thin client over Shape A's HTTP API.
 */
export class CloudClient {
  constructor(
    private readonly baseUrl: string = config.cloudApiUrl(),
    private readonly apiKey: string = config.cloudApiKey(),
  ) {}

  async startJob(req: StartJobRequest, tenantId: string): Promise<StartJobResponse> {
    const resp = await fetch(`${this.baseUrl}/v1/jobs`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Tenant-Id": tenantId,
        ...(this.apiKey ? { Authorization: `Bearer ${this.apiKey}` } : {}),
      },
      body: JSON.stringify(req),
    });
    if (!resp.ok) {
      throw new Error(`startJob failed: ${resp.status} ${await resp.text()}`);
    }
    return (await resp.json()) as StartJobResponse;
  }

  async fetchReceipt(receiptUrl: string): Promise<unknown> {
    const resp = await fetch(receiptUrl);
    if (!resp.ok) throw new Error(`fetchReceipt ${resp.status}`);
    return await resp.json();
  }
}
