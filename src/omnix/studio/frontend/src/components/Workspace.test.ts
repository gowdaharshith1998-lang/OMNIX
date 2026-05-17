import { describe, expect, it } from "vitest";
import { shallow } from "zustand/shallow";
import {
  selectAgentTabSummaries,
  type AgentTabSummary,
} from "./Workspace";
import type { AgentActionTab } from "@/state/actionDispatchStore";

function tab(overrides: Partial<AgentActionTab> = {}): AgentActionTab {
  return {
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
    ...overrides,
  };
}

describe("selectAgentTabSummaries", () => {
  it("keeps shallow equality when only tab result content changes", () => {
    const before = selectAgentTabSummaries({ agentTabs: [tab()] });
    const after = selectAgentTabSummaries({
      agentTabs: [
        tab({
          result: {
            ok: true,
            text: "streamed content changed",
            provider: "openai",
            model: "gpt-test",
            tokensIn: 1,
            tokensOut: 1,
            latencyMs: 10,
            toolSteps: [],
          },
        }),
      ],
    });

    expect(shallow<AgentTabSummary[]>(before, after)).toBe(true);
  });
});
