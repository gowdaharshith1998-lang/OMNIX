import { describe, expect, it } from "vitest";
import { createRoot } from "react-dom/client";
import { act } from "react-dom/test-utils";
import { AgentTabSurface } from "./AgentTabSurface";

describe("AgentTabSurface", () => {
  it("renders tool steps and cost cap warning", () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    act(() => {
      root.render(
        <AgentTabSurface
          tab={{
            id: "agent:test",
            status: "done",
            descriptor: {
              id: "rightrail.new_agent",
              title: "New Agent",
              kind: "agent",
              prompt: "hello",
              workspaceId: "wid",
              source: { kind: "rail", railId: "right" },
            },
            result: {
              ok: true,
              text: "```ts\nconst x = 1;\n```",
              provider: "anthropic",
              model: "m",
              tokensIn: 1,
              tokensOut: 1,
              latencyMs: 5,
              toolSteps: [
                {
                  tool: "read_code_region",
                  status: "ok",
                  truncated: true,
                },
              ],
              costCapTriggered: true,
            },
          }}
        />
      );
    });
    expect(host.textContent).toContain("tool timeline");
    expect(host.textContent).toContain("read_code_region");
    expect(host.textContent).toContain("Tool output was capped");
    act(() => root.unmount());
    host.remove();
  });

  it("shows capped banner when capReason is set", () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    act(() => {
      root.render(
        <AgentTabSurface
          tab={{
            id: "agent:test2",
            status: "done",
            descriptor: {
              id: "rightrail.new_agent",
              title: "New Agent",
              kind: "agent",
              prompt: "hello",
              workspaceId: "wid",
              source: { kind: "rail", railId: "right" },
            },
            result: {
              ok: true,
              text: "ok",
              provider: "openai",
              model: "gpt-4o",
              tokensIn: 1,
              tokensOut: 1,
              latencyMs: 3,
              toolSteps: [],
              capped: true,
              capReason: "max_iterations",
            },
          }}
        />
      );
    });
    expect(host.textContent).toContain("Stopped early");
    act(() => root.unmount());
    host.remove();
  });

  it("renders structured error message and class badge", () => {
    const host = document.createElement("div");
    document.body.appendChild(host);
    const root = createRoot(host);
    act(() => {
      root.render(
        <AgentTabSurface
          tab={{
            id: "agent:error",
            status: "error",
            error: "provider_error",
            descriptor: {
              id: "rightrail.new_agent",
              title: "New Agent",
              kind: "agent",
              prompt: "hello",
              workspaceId: "wid",
              source: { kind: "rail", railId: "right" },
            },
            result: {
              ok: false,
              text: "",
              provider: "openai",
              model: "gpt-test",
              tokensIn: 0,
              tokensOut: 0,
              latencyMs: 12,
              error: "provider_error",
              errorClass: "provider_error",
              errorMessage: "OpenAI: Incorrect API key provided (401)",
              httpStatus: 401,
              retryable: false,
              toolSteps: [],
            },
          }}
        />
      );
    });
    expect(host.textContent).toContain("OpenAI: Incorrect API key provided (401)");
    expect(host.textContent).toContain("provider_error");
    expect(host.textContent).toContain("Retry");
    act(() => root.unmount());
    host.remove();
  });
});
