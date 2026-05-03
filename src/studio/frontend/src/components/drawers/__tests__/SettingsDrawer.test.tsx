import React, { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { SettingsDrawer } from "../SettingsDrawer";

(globalThis as unknown as { IS_REACT_ACT_ENVIRONMENT: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const providerApiMock = vi.hoisted(() => ({
  deleteProviderKey: vi.fn(),
  detectProvider: vi.fn(),
  listProviderKeys: vi.fn(),
  registerProviderKey: vi.fn(),
}));

vi.mock("@/lib/providersApi", () => providerApiMock);

function render(node: React.ReactElement): { root: Root; container: HTMLDivElement } {
  const container = document.createElement("div");
  document.body.appendChild(container);
  const root = createRoot(container);
  act(() => root.render(node));
  return { root, container };
}

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
}

beforeEach(() => {
  vi.useFakeTimers();
  providerApiMock.listProviderKeys.mockResolvedValue([]);
  providerApiMock.detectProvider.mockResolvedValue({
    provider: "anthropic",
    confidence: 1,
    method: "prefix",
  });
  providerApiMock.registerProviderKey.mockResolvedValue({
    id: "global:anthropic:global",
    provider: "anthropic",
    display_name: "Anthropic",
    scope: "global",
    fingerprint: "1234",
    registered_at: "2026-05-03T00:00:00Z",
  });
  providerApiMock.deleteProviderKey.mockResolvedValue({ deleted: true });
  vi.spyOn(window, "confirm").mockReturnValue(true);
});

afterEach(() => {
  document.body.textContent = "";
  vi.useRealTimers();
  vi.restoreAllMocks();
  vi.clearAllMocks();
});

describe("SettingsDrawer provider keys", () => {
  it("shows empty state and removes placeholder copy", async () => {
    const { container } = render(<SettingsDrawer projectPath="/tmp/omnix" />);
    await flush();
    expect(container.textContent).toContain("No keys registered");
    expect(container.textContent).not.toContain("UI placeholders");
  });

  it("detects pasted key after debounce and saves", async () => {
    const { container } = render(<SettingsDrawer projectPath="/tmp/omnix" />);
    const textarea = container.querySelector("textarea") as HTMLTextAreaElement;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")?.set?.call(
        textarea,
        "sk-ant-1234"
      );
      textarea.dispatchEvent(new Event("input", { bubbles: true }));
      textarea.dispatchEvent(new Event("change", { bubbles: true }));
      vi.advanceTimersByTime(500);
    });
    await flush();
    expect(providerApiMock.detectProvider).toHaveBeenCalledWith("sk-ant-1234", undefined);
    expect(container.textContent).toContain("Detected: Anthropic");

    const save = Array.from(container.querySelectorAll("button")).find(
      (button) => button.textContent === "Save provider key"
    ) as HTMLButtonElement;
    await act(async () => save.click());
    await flush();
    expect(providerApiMock.registerProviderKey).toHaveBeenCalled();
    expect(container.textContent).toContain("****1234");
  });

  it("reveals custom endpoint fields", async () => {
    const { container } = render(<SettingsDrawer projectPath="/tmp/omnix" />);
    const select = container.querySelector("select") as HTMLSelectElement;
    await act(async () => {
      select.value = "custom";
      select.dispatchEvent(new Event("change", { bubbles: true }));
    });
    expect(container.textContent).toContain("Save provider key");
    expect((container.querySelector('input[placeholder^="Base URL"]') as HTMLInputElement)).toBeTruthy();
  });
});
