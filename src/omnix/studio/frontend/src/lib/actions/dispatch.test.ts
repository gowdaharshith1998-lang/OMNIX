import { beforeEach, describe, expect, it, vi } from "vitest";
import { dispatchAction } from "./dispatch";

vi.mock("@/lib/providersApi", () => ({
  listProviderKeys: vi.fn(async () => [
    {
      id: "k1",
      provider: "anthropic",
      scope: "global",
      fingerprint: "1234",
      registered_at: "now",
    },
  ]),
}));

describe("dispatchAction", () => {
  beforeEach(() => {
    vi.restoreAllMocks();
  });

  it("passes AbortSignal to fetch and sends workspace_id", async () => {
    let seenSignal: AbortSignal | undefined;
    let seenBody: Record<string, unknown> | undefined;
    vi.stubGlobal(
      "fetch",
      vi.fn(async (_url, init?: RequestInit) => {
        seenSignal = init?.signal as AbortSignal;
        seenBody = JSON.parse(String(init?.body));
        return new Response(
          JSON.stringify({
            ok: true,
            text: "ok",
            provider: "anthropic",
            model: "m",
            tokens_in: 1,
            tokens_out: 1,
            latency_ms: 5,
            tool_steps: [],
          }),
          { status: 200 }
        );
      })
    );
    const controller = new AbortController();
    await dispatchAction(
      {
        id: "rightrail.new_agent",
        title: "New Agent",
        kind: "agent",
        prompt: "hello",
        workspaceId: "wid",
        projectId: "pid",
        source: { kind: "rail", railId: "right" },
        tools: ["read_code_region"],
      },
      controller.signal
    );
    expect(seenSignal).toBe(controller.signal);
    expect(seenBody?.workspace_id).toBe("wid");
    expect(seenBody?.project_id).toBe("pid");
  });

  it("preserves structured dispatch error fields", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            ok: false,
            error: "provider_error",
            error_class: "provider_error",
            error_message: "Anthropic: bad key (401)",
            http_status: 401,
            provider: "anthropic",
            model: "m",
            retryable: false,
            tool_steps: [],
          }),
          { status: 200 }
        )
      )
    );

    await expect(
      dispatchAction({
        id: "rightrail.new_agent",
        title: "New Agent",
        kind: "agent",
        prompt: "hello",
        workspaceId: "wid",
        source: { kind: "rail", railId: "right" },
      })
    ).rejects.toMatchObject({
      name: "DispatchError",
      message: "Anthropic: bad key (401)",
      result: {
        errorClass: "provider_error",
        errorMessage: "Anthropic: bad key (401)",
        httpStatus: 401,
        retryable: false,
      },
    });
  });

  it("parses iterations and cap fields from action dispatch", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        new Response(
          JSON.stringify({
            ok: true,
            text: "done",
            provider: "openai",
            model: "gpt-4o",
            tokens_in: 10,
            tokens_out: 5,
            latency_ms: 20,
            tool_steps: [
              {
                tool: "get_node_context",
                status: "ok",
                result: { node: { id: "a.py::x" } },
                turn_number: 1,
                args_summary: "node_id=a.py::x",
                phase: "llm",
              },
            ],
            iterations: 2,
            capped: true,
            cap_reason: "max_iterations",
          }),
          { status: 200 }
        )
      )
    );
    const r = await dispatchAction({
      id: "x",
      title: "T",
      kind: "agent",
      prompt: "p",
      workspaceId: "w",
      source: { kind: "rail", railId: "right" },
    });
    expect(r.iterations).toBe(2);
    expect(r.capped).toBe(true);
    expect(r.capReason).toBe("max_iterations");
    expect(r.toolSteps[0]?.turn_number).toBe(1);
  });
});
