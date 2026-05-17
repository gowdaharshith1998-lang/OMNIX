import { afterEach, describe, expect, it, vi } from "vitest";
import { closeWorkspace, registerBeaconUnload } from "./workspaceLifecycle";

describe("workspaceLifecycle", () => {
  afterEach(() => {
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it("closeWorkspace swallows fetch errors", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () => {
        throw new Error("network");
      })
    );
    await expect(closeWorkspace("wid")).resolves.toBeUndefined();
  });

  it("closeWorkspace sends POST with workspace_id", async () => {
    const fetchMock = vi.fn(async () => new Response(null, { status: 200 }));
    vi.stubGlobal("fetch", fetchMock);
    await closeWorkspace("abc");
    expect(fetchMock).toHaveBeenCalledWith(
      "/api/workspace/close",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ workspace_id: "abc" }),
      })
    );
  });

  it("registerBeaconUnload removes listener on cleanup", () => {
    const addSpy = vi.spyOn(window, "addEventListener");
    const removeSpy = vi.spyOn(window, "removeEventListener");
    vi.stubGlobal(
      "navigator",
      Object.assign(navigator, {
        sendBeacon: vi.fn(() => true),
      })
    );
    const cleanup = registerBeaconUnload("z1");
    expect(addSpy).toHaveBeenCalledWith("beforeunload", expect.any(Function));
    cleanup();
    expect(removeSpy).toHaveBeenCalledWith("beforeunload", expect.any(Function));
  });
});
