import { beforeEach, describe, expect, it, vi } from "vitest";
import { useActionDispatchStore } from "./actionDispatchStore";

let lastSignal: AbortSignal | undefined;

vi.mock("@/lib/actions/dispatch", () => ({
  dispatchAction: vi.fn((_descriptor, signal?: AbortSignal) => {
    lastSignal = signal;
    return new Promise(() => undefined);
  }),
}));

describe("actionDispatchStore", () => {
  beforeEach(() => {
    lastSignal = undefined;
    useActionDispatchStore.setState({
      agentTabs: [],
      activeModal: null,
      modalQueue: [],
    });
  });

  it("aborts in-flight agent dispatch when tab closes", () => {
    const id = useActionDispatchStore.getState().openAgentTab({
      id: "rightrail.new_agent",
      title: "New Agent",
      kind: "agent",
      prompt: "hello",
      workspaceId: "wid",
      source: { kind: "rail", railId: "right" },
    });
    expect(lastSignal?.aborted).toBe(false);
    useActionDispatchStore.getState().closeAgentTab(id);
    expect(lastSignal?.aborted).toBe(true);
  });

  it("queues agent tabs beyond three in-flight dispatches", () => {
    const descriptor = {
      id: "rightrail.new_agent",
      title: "New Agent",
      kind: "agent" as const,
      prompt: "hello",
      workspaceId: "wid",
      source: { kind: "rail" as const, railId: "right" },
    };
    useActionDispatchStore.getState().openAgentTab(descriptor);
    useActionDispatchStore.getState().openAgentTab(descriptor);
    useActionDispatchStore.getState().openAgentTab(descriptor);
    useActionDispatchStore.getState().openAgentTab(descriptor);
    expect(useActionDispatchStore.getState().agentTabs.map((t) => t.status)).toEqual([
      "loading",
      "loading",
      "loading",
      "queued",
    ]);
  });
});
